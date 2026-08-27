import pytest
from pydantic import ValidationError

from app.schemas import (
    AiChatRequest,
    AiChatResponse,
    AssistantMessage,
    AssistantReplyTurn,
    AssistantToolCallTurn,
)


def test_ai_chat_request_parses_all_message_roles():
    payload = {
        "messages": [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "turns": [
                    {"type": "reply", "content": "checking"},
                    {
                        "type": "tool_call",
                        "toolCallId": "call-1",
                        "toolName": "decode_jwt",
                        "toolInput": {"token": "abc"},
                    },
                ],
            },
            {
                "role": "tool_result",
                "toolCallId": "call-1",
                "result": {"success": True, "data": {"uuid": "abc"}},
            },
        ],
        "model": "claude-opus-5",
    }

    request = AiChatRequest.model_validate(payload)

    assert len(request.messages) == 3
    assert request.messages[1].turns[1].tool_name == "decode_jwt"
    assert request.messages[2].tool_call_id == "call-1"


def test_ai_chat_request_rejects_empty_messages():
    with pytest.raises(ValidationError):
        AiChatRequest.model_validate({"messages": []})


def test_ai_chat_request_parses_tools_and_defaults_to_empty_list():
    without_tools = AiChatRequest.model_validate(
        {"messages": [{"role": "user", "content": "hi"}], "model": "claude-opus-5"}
    )
    assert without_tools.tools == []

    with_tools = AiChatRequest.model_validate(
        {
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [
                {
                    "name": "decode_jwt",
                    "description": "Decode a JWT.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"token": {"type": "string"}},
                    },
                }
            ],
            "model": "claude-opus-5",
        }
    )
    assert with_tools.tools[0].name == "decode_jwt"
    assert with_tools.tools[0].input_schema == {
        "type": "object",
        "properties": {"token": {"type": "string"}},
    }


def test_ai_chat_response_serializes_multiple_turns_as_camel_case():
    response = AiChatResponse(
        turns=[
            AssistantReplyTurn(content="checking"),
            AssistantToolCallTurn(
                tool_call_id="call-1",
                tool_name="decode_jwt",
                tool_input={"token": "abc"},
            ),
        ]
    )

    assert response.model_dump(by_alias=True) == {
        "turns": [
            {"type": "reply", "content": "checking"},
            {
                "type": "tool_call",
                "toolCallId": "call-1",
                "toolName": "decode_jwt",
                "toolInput": {"token": "abc"},
                "providerData": None,
            },
        ]
    }


def test_assistant_message_serializes_turns_as_camel_case():
    message = AssistantMessage(turns=[AssistantReplyTurn(content="hi")])

    assert message.model_dump(by_alias=True) == {
        "role": "assistant",
        "turns": [{"type": "reply", "content": "hi"}],
        "model": None,
    }


def test_ai_chat_request_requires_a_model():
    with pytest.raises(ValidationError):
        AiChatRequest.model_validate({"messages": [{"role": "user", "content": "hi"}]})


def test_ai_chat_request_accepts_a_model():
    request = AiChatRequest.model_validate(
        {"messages": [{"role": "user", "content": "hi"}], "model": "gemini-3.6-flash"}
    )

    assert request.model == "gemini-3.6-flash"


def test_assistant_message_model_defaults_to_none():
    message = AssistantMessage(turns=[AssistantReplyTurn(content="hi")])

    assert message.model is None


def test_assistant_message_model_round_trips_through_camel_case():
    message = AssistantMessage(
        turns=[AssistantReplyTurn(content="hi")], model="gemini-3.6-flash"
    )

    dumped = message.model_dump(mode="json", by_alias=True)

    assert dumped["model"] == "gemini-3.6-flash"
    assert AssistantMessage.model_validate(dumped).model == "gemini-3.6-flash"


def test_models_response_serializes_camel_case():
    from app.schemas import ModelOut, ModelsResponse

    response = ModelsResponse(
        models=[
            ModelOut(id="gemini-3.6-flash", label="Gemini 3.6 Flash", provider="gemini")
        ]
    )

    assert response.model_dump(by_alias=True) == {
        "models": [
            {
                "id": "gemini-3.6-flash",
                "label": "Gemini 3.6 Flash",
                "provider": "gemini",
            }
        ]
    }
