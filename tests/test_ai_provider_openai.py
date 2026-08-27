import json
from types import SimpleNamespace

from app.ai_providers.openai_provider import OpenAiProvider
from app.schemas import (
    AssistantMessage,
    AssistantReplyTurn,
    AssistantToolCallTurn,
    ToolDescriptor,
    ToolResultMessage,
    UserMessage,
)


def _fake_response(output):
    return SimpleNamespace(output=output)


def _message_output(text):
    return SimpleNamespace(
        type="message", content=[SimpleNamespace(type="output_text", text=text)]
    )


def _function_call_output(call_id, name, arguments):
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
    )


def test_generate_reply_returns_a_text_only_response(mocker):
    mock_client = mocker.Mock()
    mock_client.responses.create.return_value = _fake_response(
        [_message_output("Hello there!")]
    )
    mocker.patch("app.ai_providers.openai_provider.OpenAI", return_value=mock_client)

    result = OpenAiProvider().generate_reply(
        [UserMessage(content="hi")], [], "gpt-5.6-sol"
    )

    assert result == [AssistantReplyTurn(content="Hello there!")]


def test_generate_reply_passes_model_id_through(mocker):
    mock_client = mocker.Mock()
    mock_client.responses.create.return_value = _fake_response([_message_output("ok")])
    mocker.patch("app.ai_providers.openai_provider.OpenAI", return_value=mock_client)

    OpenAiProvider().generate_reply([UserMessage(content="hi")], [], "gpt-5.6-luna")

    assert mock_client.responses.create.call_args.kwargs["model"] == "gpt-5.6-luna"


def test_generate_reply_maps_function_call_output_to_a_tool_call_turn(mocker):
    mock_client = mocker.Mock()
    mock_client.responses.create.return_value = _fake_response(
        [_function_call_output("call-1", "decode_jwt", {"token": "abc"})]
    )
    mocker.patch("app.ai_providers.openai_provider.OpenAI", return_value=mock_client)

    result = OpenAiProvider().generate_reply(
        [UserMessage(content="hi")], [], "gpt-5.6-sol"
    )

    assert result == [
        AssistantToolCallTurn(
            tool_call_id="call-1", tool_name="decode_jwt", tool_input={"token": "abc"}
        )
    ]


def test_generate_reply_maps_input_items_for_a_full_round_trip(mocker):
    mock_client = mocker.Mock()
    mock_client.responses.create.return_value = _fake_response([_message_output("ok")])
    mocker.patch("app.ai_providers.openai_provider.OpenAI", return_value=mock_client)

    OpenAiProvider().generate_reply(
        [
            UserMessage(content="hi"),
            AssistantMessage(
                turns=[
                    AssistantReplyTurn(content="checking"),
                    AssistantToolCallTurn(
                        tool_call_id="call-1",
                        tool_name="decode_jwt",
                        tool_input={"token": "abc"},
                    ),
                ]
            ),
            ToolResultMessage(tool_call_id="call-1", result={"success": True}),
        ],
        [],
        "gpt-5.6-sol",
    )

    input_items = mock_client.responses.create.call_args.kwargs["input"]
    assert input_items[0] == {"role": "user", "content": "hi"}
    assert input_items[1] == {"role": "assistant", "content": "checking"}
    assert input_items[2] == {
        "type": "function_call",
        "call_id": "call-1",
        "name": "decode_jwt",
        "arguments": '{"token": "abc"}',
    }
    assert input_items[3] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '{"success": true}',
    }


def test_generate_reply_forwards_tools_as_flat_function_dicts(mocker):
    mock_client = mocker.Mock()
    mock_client.responses.create.return_value = _fake_response([_message_output("ok")])
    mocker.patch("app.ai_providers.openai_provider.OpenAI", return_value=mock_client)

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
    OpenAiProvider().generate_reply([UserMessage(content="hi")], tools, "gpt-5.6-sol")

    call_kwargs = mock_client.responses.create.call_args.kwargs
    assert call_kwargs["tools"] == [
        {
            "type": "function",
            "name": "decode_jwt",
            "description": "Decode a JWT.",
            "parameters": {
                "type": "object",
                "properties": {"token": {"type": "string"}},
            },
        }
    ]


def test_generate_reply_omits_tools_key_when_no_tools_given(mocker):
    mock_client = mocker.Mock()
    mock_client.responses.create.return_value = _fake_response([_message_output("ok")])
    mocker.patch("app.ai_providers.openai_provider.OpenAI", return_value=mock_client)

    OpenAiProvider().generate_reply([UserMessage(content="hi")], [], "gpt-5.6-sol")

    assert "tools" not in mock_client.responses.create.call_args.kwargs


def test_generate_reply_caps_max_output_tokens(mocker):
    mock_client = mocker.Mock()
    mock_client.responses.create.return_value = _fake_response([_message_output("ok")])
    mocker.patch("app.ai_providers.openai_provider.OpenAI", return_value=mock_client)

    OpenAiProvider().generate_reply([UserMessage(content="hi")], [], "gpt-5.6-sol")

    assert mock_client.responses.create.call_args.kwargs["max_output_tokens"] == 4096
