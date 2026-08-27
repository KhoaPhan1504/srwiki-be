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


def _tool_to_openai(tool: ToolDescriptor) -> dict:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
    }


def _message_to_openai_items(message: ChatMessage) -> list[dict]:
    if isinstance(message, UserMessage):
        return [{"role": "user", "content": message.content}]
    if isinstance(message, AssistantMessage):
        items: list[dict] = []
        for turn in message.turns:
            if isinstance(turn, AssistantReplyTurn):
                items.append({"role": "assistant", "content": turn.content})
            else:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": turn.tool_call_id,
                        "name": turn.tool_name,
                        "arguments": json.dumps(turn.tool_input),
                    }
                )
        return items
    assert isinstance(message, ToolResultMessage)
    return [
        {
            "type": "function_call_output",
            "call_id": message.tool_call_id,
            "output": json.dumps(message.result),
        }
    ]


def _output_to_turns(output: list) -> list[AssistantTurn]:
    turns: list[AssistantTurn] = []
    for item in output:
        if item.type == "message":
            for block in item.content:
                if block.type == "output_text":
                    turns.append(AssistantReplyTurn(content=block.text))
        elif item.type == "function_call":
            turns.append(
                AssistantToolCallTurn(
                    tool_call_id=item.call_id,
                    tool_name=item.name,
                    tool_input=json.loads(item.arguments),
                )
            )
    return turns or [AssistantReplyTurn(content="")]


class OpenAiProvider:
    id = "openai"
    env_attr = "chatgpt_api_key"
    models: ClassVar[list[ModelDescriptor]] = [
        ModelDescriptor(id="gpt-5.6-sol", label="GPT-5.6 Sol", provider="openai"),
        ModelDescriptor(id="gpt-5.6-terra", label="GPT-5.6 Terra", provider="openai"),
        ModelDescriptor(id="gpt-5.6-luna", label="GPT-5.6 Luna", provider="openai"),
    ]

    def generate_reply(
        self, messages: list[ChatMessage], tools: list[ToolDescriptor], model_id: str
    ) -> list[AssistantTurn]:
        settings = get_settings()
        client = OpenAI(api_key=settings.chatgpt_api_key)
        kwargs: dict = {"max_output_tokens": 4096}
        if tools:
            kwargs["tools"] = [_tool_to_openai(tool) for tool in tools]
        input_items = [item for m in messages for item in _message_to_openai_items(m)]
        response = client.responses.create(model=model_id, input=input_items, **kwargs)
        return _output_to_turns(response.output)
