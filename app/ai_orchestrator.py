import logging

import anthropic
import openai
from google.genai import errors as genai_errors

from app.ai_providers.registry import get_provider_for_model
from app.schemas import AssistantReplyTurn, AssistantTurn, ChatMessage, ToolDescriptor

logger = logging.getLogger(__name__)

FALLBACK_REPLY = "Sorry, I'm having trouble reaching the AI service right now. Please try again shortly."

_PROVIDER_ERRORS = (anthropic.AnthropicError, openai.OpenAIError, genai_errors.APIError)


def generate_reply(
    messages: list[ChatMessage],
    tools: list[ToolDescriptor] | None,
    model_id: str,
) -> list[AssistantTurn]:
    try:
        provider = get_provider_for_model(model_id)
        return provider.generate_reply(messages, tools or [], model_id)
    except _PROVIDER_ERRORS:
        logger.exception("AI provider call failed for model=%s", model_id)
        return [AssistantReplyTurn(content=FALLBACK_REPLY)]
