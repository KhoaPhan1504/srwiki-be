import dataclasses

import pytest

from app.ai_providers.base import ModelDescriptor


def test_model_descriptor_holds_id_label_provider():
    model = ModelDescriptor(
        id="claude-opus-5", label="Claude Opus 5", provider="anthropic"
    )

    assert model.id == "claude-opus-5"
    assert model.label == "Claude Opus 5"
    assert model.provider == "anthropic"


def test_model_descriptor_is_frozen():
    model = ModelDescriptor(id="a", label="A", provider="p")

    with pytest.raises(dataclasses.FrozenInstanceError):
        model.id = "b"
