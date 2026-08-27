from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai_providers.base import ModelDescriptor
from app.dependencies import get_current_user
from app.routers import ai
from app.schemas import AssistantReplyTurn, AssistantToolCallTurn

app = FastAPI()
app.include_router(ai.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def test_chat_returns_the_generated_turns(mocker):
    mocker.patch(
        "app.routers.ai.generate_reply",
        return_value=[AssistantReplyTurn(content="Hello!")],
    )

    response = client.post(
        "/ai/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "model": "claude-opus-5",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"turns": [{"type": "reply", "content": "Hello!"}]}


def test_chat_forwards_model_and_tools_to_the_orchestrator(mocker):
    mock_generate_reply = mocker.patch(
        "app.routers.ai.generate_reply",
        return_value=[
            AssistantToolCallTurn(
                tool_call_id="call-1",
                tool_name="decode_jwt",
                tool_input={"token": "abc"},
            )
        ],
    )

    response = client.post(
        "/ai/chat",
        json={
            "messages": [{"role": "user", "content": "decode this jwt: abc"}],
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
            "model": "gemini-3.6-flash",
        },
    )

    assert response.status_code == 200
    call_args = mock_generate_reply.call_args.args
    assert call_args[1][0].name == "decode_jwt"
    assert call_args[2] == "gemini-3.6-flash"


def test_chat_returns_400_for_an_unknown_or_unavailable_model(mocker):
    mocker.patch(
        "app.routers.ai.generate_reply",
        side_effect=ValueError("Unknown or unavailable model: nope"),
    )

    response = client.post(
        "/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "model": "nope"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Unknown or unavailable model: nope"}


def test_chat_rejects_a_request_missing_model():
    response = client.post(
        "/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )

    assert response.status_code == 422


def test_chat_rejects_empty_messages():
    response = client.post("/ai/chat", json={"messages": [], "model": "claude-opus-5"})

    assert response.status_code == 422


def test_list_models_returns_the_available_models(mocker):
    mocker.patch(
        "app.routers.ai.available_models",
        return_value=[
            ModelDescriptor(
                id="gemini-3.6-flash", label="Gemini 3.6 Flash", provider="gemini"
            )
        ],
    )

    response = client.get("/ai/models")

    assert response.status_code == 200
    assert response.json() == {
        "models": [
            {
                "id": "gemini-3.6-flash",
                "label": "Gemini 3.6 Flash",
                "provider": "gemini",
            }
        ]
    }


class TestChatAuth:
    def test_requires_bearer_token(self):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            response = client.post(
                "/ai/chat",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "model": "claude-opus-5",
                },
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides[get_current_user] = override_current_user


class TestListModelsAuth:
    def test_requires_bearer_token(self):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            response = client.get("/ai/models")
            assert response.status_code == 401
        finally:
            app.dependency_overrides[get_current_user] = override_current_user
