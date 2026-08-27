import json
from types import SimpleNamespace

from app.ai_providers.openrouter_provider import OPENROUTER_BASE_URL, OpenRouterProvider
from app.schemas import (
    AssistantMessage,
    AssistantReplyTurn,
    AssistantToolCallTurn,
    ToolDescriptor,
    ToolResultMessage,
    UserMessage,
)


def _fake_response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _message(content, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_call(id_, name, arguments):
    return SimpleNamespace(
        id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(arguments))
    )


def test_generate_reply_returns_a_text_only_response(mocker):
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _fake_response(
        _message("Hello there!")
    )
    mocker.patch(
        "app.ai_providers.openrouter_provider.OpenAI", return_value=mock_client
    )

    result = OpenRouterProvider().generate_reply(
        [UserMessage(content="hi")], [], "anthropic/claude-sonnet-5"
    )

    assert result == [AssistantReplyTurn(content="Hello there!")]


def test_generate_reply_uses_the_openrouter_base_url_and_key(mocker):
    mock_openai_class = mocker.patch(
        "app.ai_providers.openrouter_provider.OpenAI",
        return_value=mocker.Mock(
            chat=mocker.Mock(
                completions=mocker.Mock(
                    create=mocker.Mock(return_value=_fake_response(_message("ok")))
                )
            )
        ),
    )
    mocker.patch(
        "app.ai_providers.openrouter_provider.get_settings",
        return_value=SimpleNamespace(open_router_api_key="or-key-123"),
    )

    OpenRouterProvider().generate_reply(
        [UserMessage(content="hi")], [], "anthropic/claude-sonnet-5"
    )

    mock_openai_class.assert_called_once_with(
        api_key="or-key-123", base_url=OPENROUTER_BASE_URL
    )


def test_generate_reply_maps_tool_calls_from_the_response(mocker):
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _fake_response(
        _message(
            None, tool_calls=[_tool_call("call-1", "decode_jwt", {"token": "abc"})]
        )
    )
    mocker.patch(
        "app.ai_providers.openrouter_provider.OpenAI", return_value=mock_client
    )

    result = OpenRouterProvider().generate_reply(
        [UserMessage(content="hi")], [], "anthropic/claude-sonnet-5"
    )

    assert result == [
        AssistantToolCallTurn(
            tool_call_id="call-1", tool_name="decode_jwt", tool_input={"token": "abc"}
        )
    ]


def test_generate_reply_maps_messages_for_a_full_round_trip(mocker):
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _fake_response(_message("ok"))
    mocker.patch(
        "app.ai_providers.openrouter_provider.OpenAI", return_value=mock_client
    )

    OpenRouterProvider().generate_reply(
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
        "anthropic/claude-sonnet-5",
    )

    messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "user", "content": "hi"}
    assert messages[1] == {
        "role": "assistant",
        "content": "checking",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "decode_jwt", "arguments": '{"token": "abc"}'},
            }
        ],
    }
    assert messages[2] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"success": true}',
    }


def test_generate_reply_forwards_tools_in_the_nested_function_shape(mocker):
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _fake_response(_message("ok"))
    mocker.patch(
        "app.ai_providers.openrouter_provider.OpenAI", return_value=mock_client
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
    OpenRouterProvider().generate_reply(
        [UserMessage(content="hi")], tools, "anthropic/claude-sonnet-5"
    )

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "decode_jwt",
                "description": "Decode a JWT.",
                "parameters": {
                    "type": "object",
                    "properties": {"token": {"type": "string"}},
                },
            },
        }
    ]


def test_generate_reply_caps_max_tokens(mocker):
    mock_client = mocker.Mock()
    mock_client.chat.completions.create.return_value = _fake_response(_message("ok"))
    mocker.patch(
        "app.ai_providers.openrouter_provider.OpenAI", return_value=mock_client
    )

    OpenRouterProvider().generate_reply(
        [UserMessage(content="hi")], [], "anthropic/claude-sonnet-5"
    )

    assert mock_client.chat.completions.create.call_args.kwargs["max_tokens"] == 4096
