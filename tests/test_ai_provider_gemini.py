from types import SimpleNamespace

from app.ai_providers.gemini_provider import GeminiProvider
from app.schemas import (
    AssistantMessage,
    AssistantReplyTurn,
    AssistantToolCallTurn,
    ToolDescriptor,
    ToolResultMessage,
    UserMessage,
)


def _fake_response(*parts):
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=list(parts)))]
    )


def _text_part(text):
    return SimpleNamespace(text=text, function_call=None)


def _function_call_part(name, args, thought_signature=None):
    return SimpleNamespace(
        text=None,
        function_call=SimpleNamespace(name=name, args=args),
        thought_signature=thought_signature,
    )


def test_generate_reply_returns_a_text_only_response(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(
        _text_part("Hello there!")
    )
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    result = GeminiProvider().generate_reply(
        [UserMessage(content="hi")], [], "gemini-3.6-flash"
    )

    assert result == [AssistantReplyTurn(content="Hello there!")]


def test_generate_reply_passes_model_id_through(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    GeminiProvider().generate_reply(
        [UserMessage(content="hi")], [], "gemini-3.1-pro-preview"
    )

    assert (
        mock_client.models.generate_content.call_args.kwargs["model"]
        == "gemini-3.1-pro-preview"
    )


def test_generate_reply_maps_a_function_call_with_a_synthetic_call_id(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(
        _function_call_part("decode_jwt", {"token": "abc"})
    )
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )
    mocker.patch(
        "app.ai_providers.gemini_provider.uuid.uuid4", return_value="fake-uuid"
    )

    result = GeminiProvider().generate_reply(
        [UserMessage(content="hi")], [], "gemini-3.6-flash"
    )

    assert result == [
        AssistantToolCallTurn(
            tool_call_id="fake-uuid",
            tool_name="decode_jwt",
            tool_input={"token": "abc"},
        )
    ]


def test_generate_reply_captures_thought_signature_as_base64_provider_data(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(
        _function_call_part(
            "decode_jwt", {"token": "abc"}, thought_signature=b"\x01\x02\xff"
        )
    )
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    result = GeminiProvider().generate_reply(
        [UserMessage(content="hi")], [], "gemini-3.6-flash"
    )

    assert result[0].provider_data == "AQL/"  # base64 of b"\x01\x02\xff"


def test_generate_reply_omits_provider_data_when_no_thought_signature(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(
        _function_call_part("decode_jwt", {"token": "abc"})
    )
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    result = GeminiProvider().generate_reply(
        [UserMessage(content="hi")], [], "gemini-3.6-flash"
    )

    assert result[0].provider_data is None


def test_generate_reply_resends_thought_signature_when_replaying_a_tool_call(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    GeminiProvider().generate_reply(
        [
            UserMessage(content="hi"),
            AssistantMessage(
                turns=[
                    AssistantToolCallTurn(
                        tool_call_id="call-1",
                        tool_name="decode_jwt",
                        tool_input={"token": "abc"},
                        provider_data="AQL/",  # base64 of b"\x01\x02\xff"
                    )
                ]
            ),
            ToolResultMessage(tool_call_id="call-1", result={"success": True}),
        ],
        [],
        "gemini-3.6-flash",
    )

    contents = mock_client.models.generate_content.call_args.kwargs["contents"]
    assert contents[1] == {
        "role": "model",
        "parts": [
            {
                "function_call": {"name": "decode_jwt", "args": {"token": "abc"}},
                "thought_signature": b"\x01\x02\xff",
            }
        ],
    }


def test_generate_reply_maps_user_messages_to_user_role_parts(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    GeminiProvider().generate_reply([UserMessage(content="hi")], [], "gemini-3.6-flash")

    contents = mock_client.models.generate_content.call_args.kwargs["contents"]
    assert contents == [{"role": "user", "parts": [{"text": "hi"}]}]


def test_generate_reply_resolves_tool_result_to_the_original_function_name(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    GeminiProvider().generate_reply(
        [
            UserMessage(content="hi"),
            AssistantMessage(
                turns=[
                    AssistantToolCallTurn(
                        tool_call_id="call-1",
                        tool_name="decode_jwt",
                        tool_input={"token": "abc"},
                    )
                ]
            ),
            ToolResultMessage(tool_call_id="call-1", result={"success": True}),
        ],
        [],
        "gemini-3.6-flash",
    )

    contents = mock_client.models.generate_content.call_args.kwargs["contents"]
    assert contents[2] == {
        "role": "user",
        "parts": [
            {"function_response": {"name": "decode_jwt", "response": {"success": True}}}
        ],
    }


def test_generate_reply_forwards_tools_as_function_declarations(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    tools = [
        ToolDescriptor(
            name="decode_jwt",
            description="Decode a JWT.",
            input_schema={
                "type": "object",
                "properties": {"token": {"type": "string"}},
            },
        )
    ]
    GeminiProvider().generate_reply(
        [UserMessage(content="hi")], tools, "gemini-3.6-flash"
    )

    # The google-genai SDK coerces the raw dict into typed Tool/FunctionDeclaration
    # objects (and JSON-schema "object"/"string" into its own Type enum) — assert on
    # the meaningful fields rather than exact dict equality against SDK internals.
    config = mock_client.models.generate_content.call_args.kwargs["config"]
    declarations = config.tools[0].function_declarations
    assert len(declarations) == 1
    assert declarations[0].name == "decode_jwt"
    assert declarations[0].description == "Decode a JWT."


def test_generate_reply_sanitizes_a_mixed_type_enum_for_gemini(mocker):
    # Gemini's Schema type requires enum values to all be strings and `type`
    # to be a single value — zod-to-json-schema produces {"type": ["number",
    # "string"], "enum": [2, 4, "tab"]} for z.union([z.literal(2),
    # z.literal(4), z.literal('tab')]) (format_json's `indent` param), which
    # the real google-genai SDK rejects with a pydantic ValidationError
    # unless this gets sanitized first.
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    tools = [
        ToolDescriptor(
            name="format_json",
            description="Pretty-print JSON.",
            input_schema={
                "type": "object",
                "properties": {
                    "indent": {"type": ["number", "string"], "enum": [2, 4, "tab"]}
                },
            },
        )
    ]

    # Must not raise — this is the exact shape that reproduced the live bug.
    GeminiProvider().generate_reply(
        [UserMessage(content="hi")], tools, "gemini-3.6-flash"
    )

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    indent_schema = (
        config.tools[0].function_declarations[0].parameters.properties["indent"]
    )
    assert indent_schema.enum == ["2", "4", "tab"]


def test_generate_reply_sanitizes_const_inside_anyof_for_gemini(mocker):
    # zod-to-json-schema turns z.discriminatedUnion('mode', [...]) (used by
    # convert_timestamp/convert_unit) into anyOf branches whose discriminator
    # field is {"const": "..."}. Gemini's Schema has no `const` field at all
    # ("Extra inputs are not permitted") — this must become a 1-item enum.
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    tools = [
        ToolDescriptor(
            name="convert_timestamp",
            description="Convert a timestamp.",
            input_schema={
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {"mode": {"const": "timestampToDate"}},
                    },
                    {
                        "type": "object",
                        "properties": {"mode": {"const": "dateToTimestamp"}},
                    },
                ]
            },
        )
    ]

    GeminiProvider().generate_reply(
        [UserMessage(content="hi")], tools, "gemini-3.6-flash"
    )

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    branches = config.tools[0].function_declarations[0].parameters.any_of
    assert branches[0].properties["mode"].enum == ["timestampToDate"]
    assert branches[1].properties["mode"].enum == ["dateToTimestamp"]


def test_generate_reply_strips_additional_properties_for_gemini(mocker):
    # zod-to-json-schema emits additionalProperties: false on every
    # z.object()-based tool schema. The google-genai SDK accepts it fine when
    # *constructing* the Python Schema object (it's a real field, aliased
    # from additionalProperties), but its outgoing wire serialization sends
    # it back out as the raw Python attribute name `additional_properties`
    # instead of the camelCase Gemini's REST API actually expects — a live
    # call then fails with "Unknown name additional_properties: Cannot find
    # field" even though schema construction itself never raised. Dropping
    # the key before it reaches the SDK sidesteps the whole interop trap.
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    tools = [
        ToolDescriptor(
            name="decode_jwt",
            description="Decode a JWT.",
            input_schema={
                "type": "object",
                "properties": {"token": {"type": "string"}},
                "additionalProperties": False,
            },
        )
    ]
    GeminiProvider().generate_reply(
        [UserMessage(content="hi")], tools, "gemini-3.6-flash"
    )

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    parameters = config.tools[0].function_declarations[0].parameters
    assert parameters.additional_properties is None


def test_generate_reply_omits_tools_from_config_when_no_tools_given(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    GeminiProvider().generate_reply([UserMessage(content="hi")], [], "gemini-3.6-flash")

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.tools is None


def test_generate_reply_caps_max_output_tokens(mocker):
    mock_client = mocker.Mock()
    mock_client.models.generate_content.return_value = _fake_response(_text_part("ok"))
    mocker.patch(
        "app.ai_providers.gemini_provider.genai.Client", return_value=mock_client
    )

    GeminiProvider().generate_reply([UserMessage(content="hi")], [], "gemini-3.6-flash")

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.max_output_tokens == 4096
