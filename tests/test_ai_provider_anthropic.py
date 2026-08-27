from types import SimpleNamespace

from app.ai_providers.anthropic_provider import AnthropicProvider
from app.schemas import (
    AssistantMessage,
    AssistantReplyTurn,
    AssistantToolCallTurn,
    ToolDescriptor,
    ToolResultMessage,
    UserMessage,
)


def _fake_response(*blocks):
    return SimpleNamespace(content=list(blocks))


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def test_generate_reply_returns_a_text_only_response(mocker):
    mock_client = mocker.Mock()
    mock_client.messages.create.return_value = _fake_response(
        _text_block("Hello there!")
    )
    mocker.patch(
        "app.ai_providers.anthropic_provider.anthropic.Anthropic",
        return_value=mock_client,
    )

    result = AnthropicProvider().generate_reply(
        [UserMessage(content="hi")], [], "claude-opus-5"
    )

    assert result == [AssistantReplyTurn(content="Hello there!")]


def test_generate_reply_passes_model_id_through(mocker):
    mock_client = mocker.Mock()
    mock_client.messages.create.return_value = _fake_response(_text_block("ok"))
    mocker.patch(
        "app.ai_providers.anthropic_provider.anthropic.Anthropic",
        return_value=mock_client,
    )

    AnthropicProvider().generate_reply(
        [UserMessage(content="hi")], [], "claude-sonnet-5"
    )

    assert mock_client.messages.create.call_args.kwargs["model"] == "claude-sonnet-5"


def test_generate_reply_maps_text_and_tool_use_blocks_to_turns(mocker):
    mock_client = mocker.Mock()
    mock_client.messages.create.return_value = _fake_response(
        _text_block("Let me check that."),
        _tool_use_block("call-1", "decode_jwt", {"token": "abc"}),
    )
    mocker.patch(
        "app.ai_providers.anthropic_provider.anthropic.Anthropic",
        return_value=mock_client,
    )

    result = AnthropicProvider().generate_reply(
        [UserMessage(content="hi")], [], "claude-opus-5"
    )

    assert result == [
        AssistantReplyTurn(content="Let me check that."),
        AssistantToolCallTurn(
            tool_call_id="call-1", tool_name="decode_jwt", tool_input={"token": "abc"}
        ),
    ]


def test_generate_reply_forwards_tools_to_claude(mocker):
    mock_client = mocker.Mock()
    mock_client.messages.create.return_value = _fake_response(_text_block("ok"))
    mocker.patch(
        "app.ai_providers.anthropic_provider.anthropic.Anthropic",
        return_value=mock_client,
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
    AnthropicProvider().generate_reply(
        [UserMessage(content="hi")], tools, "claude-opus-5"
    )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["tools"] == [
        {
            "name": "decode_jwt",
            "description": "Decode a JWT.",
            "input_schema": {
                "type": "object",
                "properties": {"token": {"type": "string"}},
            },
        }
    ]


def test_generate_reply_omits_tools_key_when_no_tools_given(mocker):
    mock_client = mocker.Mock()
    mock_client.messages.create.return_value = _fake_response(_text_block("ok"))
    mocker.patch(
        "app.ai_providers.anthropic_provider.anthropic.Anthropic",
        return_value=mock_client,
    )

    AnthropicProvider().generate_reply([UserMessage(content="hi")], [], "claude-opus-5")

    assert "tools" not in mock_client.messages.create.call_args.kwargs


def test_generate_reply_maps_assistant_message_and_tool_result_message(mocker):
    mock_client = mocker.Mock()
    mock_client.messages.create.return_value = _fake_response(_text_block("ok"))
    mocker.patch(
        "app.ai_providers.anthropic_provider.anthropic.Anthropic",
        return_value=mock_client,
    )

    AnthropicProvider().generate_reply(
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
            ToolResultMessage(
                tool_call_id="call-1", result={"success": True, "data": {}}
            ),
        ],
        [],
        "claude-opus-5",
    )

    messages = mock_client.messages.create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "user", "content": "hi"}
    assert messages[1] == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "checking"},
            {
                "type": "tool_use",
                "id": "call-1",
                "name": "decode_jwt",
                "input": {"token": "abc"},
            },
        ],
    }
    assert messages[2] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "call-1",
                "content": '{"success": true, "data": {}}',
            }
        ],
    }
