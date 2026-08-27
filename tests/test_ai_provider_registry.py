from types import SimpleNamespace

import pytest

from app.ai_providers.registry import (
    available_models,
    available_providers,
    get_provider_for_model,
)


def _settings(**keys):
    defaults = {
        "anthropic_api_key": None,
        "gemini_api_key": None,
        "chatgpt_api_key": None,
        "open_router_api_key": None,
    }
    defaults.update(keys)
    return SimpleNamespace(**defaults)


def test_available_providers_returns_none_when_no_keys_set(mocker):
    mocker.patch("app.ai_providers.registry.get_settings", return_value=_settings())

    assert available_providers() == []


def test_available_providers_returns_only_anthropic_when_only_that_key_is_set(mocker):
    mocker.patch(
        "app.ai_providers.registry.get_settings",
        return_value=_settings(anthropic_api_key="sk-ant-x"),
    )

    providers = available_providers()

    assert [p.id for p in providers] == ["anthropic"]


def test_available_providers_returns_all_four_when_all_keys_are_set(mocker):
    mocker.patch(
        "app.ai_providers.registry.get_settings",
        return_value=_settings(
            anthropic_api_key="a",
            gemini_api_key="g",
            chatgpt_api_key="c",
            open_router_api_key="o",
        ),
    )

    providers = available_providers()

    assert {p.id for p in providers} == {"anthropic", "gemini", "openai", "openrouter"}


def test_available_models_only_lists_models_from_enabled_providers(mocker):
    mocker.patch(
        "app.ai_providers.registry.get_settings",
        return_value=_settings(gemini_api_key="g"),
    )

    models = available_models()

    assert models
    assert all(m.provider == "gemini" for m in models)


def test_get_provider_for_model_resolves_a_known_available_model(mocker):
    mocker.patch(
        "app.ai_providers.registry.get_settings",
        return_value=_settings(anthropic_api_key="a"),
    )

    provider = get_provider_for_model("claude-opus-5")

    assert provider.id == "anthropic"


def test_get_provider_for_model_raises_for_an_unknown_model(mocker):
    mocker.patch(
        "app.ai_providers.registry.get_settings",
        return_value=_settings(anthropic_api_key="a"),
    )

    with pytest.raises(ValueError):
        get_provider_for_model("does-not-exist")


def test_get_provider_for_model_raises_when_the_models_provider_key_is_missing(mocker):
    mocker.patch("app.ai_providers.registry.get_settings", return_value=_settings())

    with pytest.raises(ValueError):
        get_provider_for_model("claude-opus-5")
