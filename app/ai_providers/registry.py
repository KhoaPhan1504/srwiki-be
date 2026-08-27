from app.ai_providers.anthropic_provider import AnthropicProvider
from app.ai_providers.base import ModelDescriptor, Provider
from app.ai_providers.gemini_provider import GeminiProvider
from app.ai_providers.openai_provider import OpenAiProvider
from app.ai_providers.openrouter_provider import OpenRouterProvider
from app.config import get_settings

PROVIDERS: dict[str, Provider] = {
    "anthropic": AnthropicProvider(),
    "gemini": GeminiProvider(),
    "openai": OpenAiProvider(),
    "openrouter": OpenRouterProvider(),
}


def available_providers() -> list[Provider]:
    settings = get_settings()
    return [p for p in PROVIDERS.values() if getattr(settings, p.env_attr, None)]


def available_models() -> list[ModelDescriptor]:
    return [model for provider in available_providers() for model in provider.models]


def get_provider_for_model(model_id: str) -> Provider:
    for provider in available_providers():
        for model in provider.models:
            if model.id == model_id:
                return provider
    raise ValueError(f"Unknown or unavailable model: {model_id}")
