import json
from typing import ClassVar

import anthropic

from app.ai_providers.base import ModelDescriptor
from app.config import get_settings
from app.schemas import (
    AssistantMessage,
    AssistantReplyTurn,
    AssistantToolCallTurn,
    AssistantTurn,
    ChatMessage,
    ToolDescriptor,
    ToolResultMessage,
    UserMessage,
)


def _turn_to_block(turn: AssistantTurn) -> dict:
    if isinstance(turn, AssistantReplyTurn):
        return {"type": "text", "text": turn.content}
    return {
        "type": "tool_use",
        "id": turn.tool_call_id,
        "name": turn.tool_name,
        "input": turn.tool_input,
    }


def _message_to_anthropic(message: ChatMessage) -> dict:
    if isinstance(message, UserMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, AssistantMessage):
        return {
            "role": "assistant",
            "content": [_turn_to_block(turn) for turn in message.turns],
        }
    assert isinstance(message, ToolResultMessage)
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": json.dumps(message.result),
            }
        ],
    }


def _tool_to_anthropic(tool: ToolDescriptor) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def _content_to_turns(content: list) -> list[AssistantTurn]:
    turns: list[AssistantTurn] = []
    for block in content:
        if block.type == "text":
            turns.append(AssistantReplyTurn(content=block.text))
        elif block.type == "tool_use":
            turns.append(
                AssistantToolCallTurn(
                    tool_call_id=block.id, tool_name=block.name, tool_input=block.input
                )
            )
    return turns or [AssistantReplyTurn(content="")]


class AnthropicProvider:
    id = "anthropic"
    env_attr = "anthropic_api_key"
    models: ClassVar[list[ModelDescriptor]] = [
        ModelDescriptor(
            id="claude-opus-5", label="Claude Opus 5", provider="anthropic"
        ),
        ModelDescriptor(
            id="claude-sonnet-5", label="Claude Sonnet 5", provider="anthropic"
        ),
        ModelDescriptor(
            id="claude-fable-5", label="Claude Fable 5", provider="anthropic"
        ),
    ]

    def generate_reply(
        self, messages: list[ChatMessage], tools: list[ToolDescriptor], model_id: str
    ) -> list[AssistantTurn]:
        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        kwargs: dict = {}
        if tools:
            kwargs["tools"] = [_tool_to_anthropic(tool) for tool in tools]
        response = client.messages.create(
            model=model_id,
            max_tokens=4096,
            messages=[_message_to_anthropic(message) for message in messages],
            **kwargs,
        )
        return _content_to_turns(response.content)
