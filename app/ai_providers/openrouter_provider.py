import json
from typing import ClassVar

from openai import OpenAI

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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _tool_to_openrouter(tool: ToolDescriptor) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _message_to_openrouter(message: ChatMessage) -> dict:
    if isinstance(message, UserMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, AssistantMessage):
        reply_text = "\n".join(
            turn.content
            for turn in message.turns
            if isinstance(turn, AssistantReplyTurn)
        )
        tool_calls = [
            {
                "id": turn.tool_call_id,
                "type": "function",
                "function": {
                    "name": turn.tool_name,
                    "arguments": json.dumps(turn.tool_input),
                },
            }
            for turn in message.turns
            if isinstance(turn, AssistantToolCallTurn)
        ]
        result: dict = {"role": "assistant", "content": reply_text or None}
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result
    assert isinstance(message, ToolResultMessage)
    return {
        "role": "tool",
        "tool_call_id": message.tool_call_id,
        "content": json.dumps(message.result),
    }


def _message_to_turns(message) -> list[AssistantTurn]:
    turns: list[AssistantTurn] = []
    if message.content:
        turns.append(AssistantReplyTurn(content=message.content))
    for call in message.tool_calls or []:
        turns.append(
            AssistantToolCallTurn(
                tool_call_id=call.id,
                tool_name=call.function.name,
                tool_input=json.loads(call.function.arguments),
            )
        )
    return turns or [AssistantReplyTurn(content="")]


class OpenRouterProvider:
    id = "openrouter"
    env_attr = "open_router_api_key"
    models: ClassVar[list[ModelDescriptor]] = [
        ModelDescriptor(
            id="anthropic/claude-sonnet-5",
            label="Claude Sonnet 5 (OpenRouter)",
            provider="openrouter",
        ),
        ModelDescriptor(
            id="openai/gpt-5.6-sol",
            label="GPT-5.6 Sol (OpenRouter)",
            provider="openrouter",
        ),
        ModelDescriptor(
            id="google/gemini-2.5-flash",
            label="Gemini 2.5 Flash (OpenRouter)",
            provider="openrouter",
        ),
        ModelDescriptor(
            id="meta-llama/llama-4-maverick",
            label="Llama 4 Maverick (OpenRouter)",
            provider="openrouter",
        ),
        ModelDescriptor(
            id="deepseek/deepseek-v4-pro",
            label="DeepSeek V4 Pro (OpenRouter)",
            provider="openrouter",
        ),
    ]

    def generate_reply(
        self, messages: list[ChatMessage], tools: list[ToolDescriptor], model_id: str
    ) -> list[AssistantTurn]:
        settings = get_settings()
        client = OpenAI(
            api_key=settings.open_router_api_key, base_url=OPENROUTER_BASE_URL
        )
        kwargs: dict = {"max_tokens": 4096}
        if tools:
            kwargs["tools"] = [_tool_to_openrouter(tool) for tool in tools]
        response = client.chat.completions.create(
            model=model_id,
            messages=[_message_to_openrouter(m) for m in messages],
            **kwargs,
        )
        return _message_to_turns(response.choices[0].message)
