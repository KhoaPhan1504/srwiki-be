import anthropic
import openai
import pytest

from app.schemas import AssistantReplyTurn, UserMessage


class _FakeProvider:
    def __init__(self, turns=None, error=None):
        self._turns = turns
        self._error = error
        self.calls = []

    def generate_reply(self, messages, tools, model_id):
        self.calls.append((messages, tools, model_id))
        if self._error:
            raise self._error
        return self._turns


def test_generate_reply_delegates_to_the_resolved_provider(mocker):
    fake_provider = _FakeProvider(
        turns=[AssistantReplyTurn(content="hi from provider")]
    )
    mocker.patch(
        "app.ai_orchestrator.get_provider_for_model", return_value=fake_provider
    )

    from app.ai_orchestrator import generate_reply

    result = generate_reply([UserMessage(content="hi")], [], "claude-opus-5")

    assert result == [AssistantReplyTurn(content="hi from provider")]
    assert fake_provider.calls == [([UserMessage(content="hi")], [], "claude-opus-5")]


def test_generate_reply_defaults_tools_to_an_empty_list(mocker):
    fake_provider = _FakeProvider(turns=[AssistantReplyTurn(content="ok")])
    mocker.patch(
        "app.ai_orchestrator.get_provider_for_model", return_value=fake_provider
    )

    from app.ai_orchestrator import generate_reply

    generate_reply([UserMessage(content="hi")], None, "claude-opus-5")

    assert fake_provider.calls[0][1] == []


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=None),
        openai.APIConnectionError(request=None),
    ],
)
def test_generate_reply_degrades_gracefully_on_a_provider_sdk_error(mocker, error):
    fake_provider = _FakeProvider(error=error)
    mocker.patch(
        "app.ai_orchestrator.get_provider_for_model", return_value=fake_provider
    )

    from app.ai_orchestrator import generate_reply

    result = generate_reply([UserMessage(content="hi")], [], "claude-opus-5")

    assert len(result) == 1
    assert result[0].type == "reply"
    assert result[0].content


def test_generate_reply_does_not_swallow_an_unknown_model_error(mocker):
    mocker.patch(
        "app.ai_orchestrator.get_provider_for_model",
        side_effect=ValueError("Unknown or unavailable model: nope"),
    )

    from app.ai_orchestrator import generate_reply

    with pytest.raises(ValueError):
        generate_reply([UserMessage(content="hi")], [], "nope")
