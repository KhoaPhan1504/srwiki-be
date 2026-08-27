import base64
import uuid
from typing import ClassVar

from google import genai
from google.genai import types

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


def _build_tool_call_id_to_name(messages: list[ChatMessage]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for message in messages:
        if isinstance(message, AssistantMessage):
            for turn in message.turns:
                if isinstance(turn, AssistantToolCallTurn):
                    lookup[turn.tool_call_id] = turn.tool_name
    return lookup


def _message_to_gemini(message: ChatMessage, tool_names: dict[str, str]) -> dict:
    if isinstance(message, UserMessage):
        return {"role": "user", "parts": [{"text": message.content}]}
    if isinstance(message, AssistantMessage):
        parts: list[dict] = []
        for turn in message.turns:
            if isinstance(turn, AssistantReplyTurn):
                parts.append({"text": turn.content})
            else:
                part: dict = {
                    "function_call": {"name": turn.tool_name, "args": turn.tool_input}
                }
                if turn.provider_data:
                    part["thought_signature"] = base64.b64decode(turn.provider_data)
                parts.append(part)
        return {"role": "model", "parts": parts}
    assert isinstance(message, ToolResultMessage)
    return {
        "role": "user",
        "parts": [
            {
                "function_response": {
                    "name": tool_names[message.tool_call_id],
                    "response": message.result,
                }
            }
        ],
    }


def _sanitize_schema_for_gemini(schema):
    """Gemini's function-calling Schema is a strict subset of JSON Schema: no
    `const` field at all, `enum` values must all be strings, and `type` must
    be a single value, not a list. Our tool schemas come from zod-to-json-
    schema (built for Anthropic's more permissive JSON Schema support), so
    z.literal/z.discriminatedUnion-based tools produce shapes Gemini's SDK
    rejects with a pydantic ValidationError unless sanitized first.

    `additionalProperties` (which zod-to-json-schema emits on every
    z.object()) is a separate trap: the SDK accepts it fine when building the
    Python Schema object (it's a real field, aliased from the camelCase JSON
    key), but its outgoing wire serialization sends it back out as the raw
    Python attribute name `additional_properties` instead of the camelCase
    Gemini's REST API expects, so a live call fails with "Unknown name
    additional_properties: Cannot find field" even though nothing raised
    locally. Dropping the key sidesteps the whole interop trap."""
    if not isinstance(schema, dict):
        return schema

    schema = dict(schema)
    schema.pop("additionalProperties", None)

    if "const" in schema:
        schema["enum"] = [str(schema.pop("const"))]

    if "enum" in schema:
        schema["enum"] = [str(value) for value in schema["enum"]]

    if isinstance(schema.get("type"), list):
        non_null_types = [t for t in schema["type"] if t != "null"]
        schema["type"] = non_null_types[0] if non_null_types else "string"

    if isinstance(schema.get("properties"), dict):
        schema["properties"] = {
            key: _sanitize_schema_for_gemini(value)
            for key, value in schema["properties"].items()
        }

    if "items" in schema:
        schema["items"] = _sanitize_schema_for_gemini(schema["items"])

    for key in ("anyOf", "oneOf", "allOf"):
        if isinstance(schema.get(key), list):
            schema[key] = [
                _sanitize_schema_for_gemini(branch) for branch in schema[key]
            ]

    return schema


def _tool_to_gemini(tool: ToolDescriptor) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": _sanitize_schema_for_gemini(tool.input_schema),
    }


def _content_to_turns(response) -> list[AssistantTurn]:
    turns: list[AssistantTurn] = []
    for part in response.candidates[0].content.parts:
        if part.text:
            turns.append(AssistantReplyTurn(content=part.text))
        elif part.function_call:
            provider_data = None
            if part.thought_signature:
                provider_data = base64.b64encode(part.thought_signature).decode()
            turns.append(
                AssistantToolCallTurn(
                    tool_call_id=str(uuid.uuid4()),
                    tool_name=part.function_call.name,
                    tool_input=dict(part.function_call.args),
                    provider_data=provider_data,
                )
            )
    return turns or [AssistantReplyTurn(content="")]


class GeminiProvider:
    id = "gemini"
    env_attr = "gemini_api_key"
    models: ClassVar[list[ModelDescriptor]] = [
        ModelDescriptor(
            id="gemini-3.6-flash", label="Gemini 3.6 Flash", provider="gemini"
        ),
        ModelDescriptor(
            id="gemini-3.5-flash", label="Gemini 3.5 Flash", provider="gemini"
        ),
        ModelDescriptor(
            id="gemini-3.1-pro-preview", label="Gemini 3.1 Pro", provider="gemini"
        ),
    ]

    def generate_reply(
        self, messages: list[ChatMessage], tools: list[ToolDescriptor], model_id: str
    ) -> list[AssistantTurn]:
        settings = get_settings()
        client = genai.Client(api_key=settings.gemini_api_key)
        tool_names = _build_tool_call_id_to_name(messages)
        config_kwargs: dict = {"max_output_tokens": 4096}
        if tools:
            config_kwargs["tools"] = [
                {"function_declarations": [_tool_to_gemini(t) for t in tools]}
            ]
        config = types.GenerateContentConfig(**config_kwargs)
        response = client.models.generate_content(
            model=model_id,
            contents=[_message_to_gemini(m, tool_names) for m in messages],
            config=config,
        )
        return _content_to_turns(response)
