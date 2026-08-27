from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.routers import ai_conversations

app = FastAPI()
app.include_router(ai_conversations.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)

CONVERSATION_ID = "11111111-1111-1111-1111-111111111111"
MISSING_CONVERSATION_ID = "22222222-2222-2222-2222-222222222222"

CONVERSATION_ROW = {
    "id": CONVERSATION_ID,
    "user_id": "user-1",
    "title": "My chat",
    "created_at": "2026-08-26T00:00:00+00:00",
    "updated_at": "2026-08-26T00:00:00+00:00",
}

MESSAGE_ROW = {
    "id": "msg-1",
    "conversation_id": CONVERSATION_ID,
    "user_id": "user-1",
    "seq": 1,
    "payload": {"role": "user", "content": "hi"},
    "created_at": "2026-08-26T00:00:01+00:00",
}


def test_list_conversations_empty(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.get("/ai/conversations")

    assert response.status_code == 200
    assert response.json() == []


def test_list_conversations_returns_rows_sorted_by_the_query(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(
        data=[CONVERSATION_ROW]
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.get("/ai/conversations")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == CONVERSATION_ID
    fake_client.table.return_value.select.return_value.eq.return_value.order.assert_called_with(
        "updated_at", desc=True
    )


def test_create_conversation_inserts_scoped_to_user(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.insert.return_value.execute.return_value = (
        SimpleNamespace(data=[CONVERSATION_ROW])
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.post("/ai/conversations", json={"title": "My chat"})

    assert response.status_code == 201
    assert response.json()["id"] == CONVERSATION_ID
    inserted = fake_client.table.return_value.insert.call_args[0][0]
    assert inserted == {"user_id": "user-1", "title": "My chat"}


def test_create_conversation_defaults_title_when_omitted(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.insert.return_value.execute.return_value = (
        SimpleNamespace(data=[CONVERSATION_ROW])
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    client.post("/ai/conversations", json={})

    inserted = fake_client.table.return_value.insert.call_args[0][0]
    assert inserted["title"] == "New conversation"


def _fake_client_for_get(mocker, conversation_data, message_rows):
    fake_client = mocker.MagicMock()
    fake_conversations_query = mocker.MagicMock()
    fake_conversations_query.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=conversation_data
    )
    fake_messages_query = mocker.MagicMock()
    fake_messages_query.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(
        data=message_rows
    )
    fake_client.table.side_effect = lambda name: (
        fake_conversations_query if name == "ai_conversations" else fake_messages_query
    )
    return fake_client, fake_conversations_query, fake_messages_query


def test_get_conversation_returns_messages_in_order(mocker):
    fake_client, _, fake_messages_query = _fake_client_for_get(
        mocker, CONVERSATION_ROW, [MESSAGE_ROW]
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.get(f"/ai/conversations/{CONVERSATION_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == CONVERSATION_ID
    assert body["messages"][0]["payload"] == {"role": "user", "content": "hi"}
    fake_messages_query.select.return_value.eq.return_value.eq.return_value.order.assert_called_with(
        "seq"
    )


def test_get_conversation_not_found_returns_404(mocker):
    fake_client, _, _ = _fake_client_for_get(mocker, None, [])
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.get(f"/ai/conversations/{MISSING_CONVERSATION_ID}")

    assert response.status_code == 404


def test_rename_conversation_updates_scoped_row(mocker):
    fake_client = mocker.MagicMock()
    renamed = {**CONVERSATION_ROW, "title": "Renamed"}
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[renamed]
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.patch(
        f"/ai/conversations/{CONVERSATION_ID}", json={"title": "Renamed"}
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    fake_client.table.return_value.update.return_value.eq.assert_called_with(
        "id", CONVERSATION_ID
    )
    fake_client.table.return_value.update.return_value.eq.return_value.eq.assert_called_with(
        "user_id", "user-1"
    )


def test_rename_conversation_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.patch(
        f"/ai/conversations/{MISSING_CONVERSATION_ID}", json={"title": "Renamed"}
    )

    assert response.status_code == 404


def test_delete_conversation_removes_scoped_row(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[CONVERSATION_ROW]
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.delete(f"/ai/conversations/{CONVERSATION_ID}")

    assert response.status_code == 204


def test_delete_conversation_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.delete(f"/ai/conversations/{MISSING_CONVERSATION_ID}")

    assert response.status_code == 404


def _fake_client_for_append(mocker, conversation_exists_data, inserted_rows):
    fake_client = mocker.MagicMock()
    fake_conversations_query = mocker.MagicMock()
    fake_conversations_query.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=conversation_exists_data
    )
    fake_conversations_query.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    fake_messages_query = mocker.MagicMock()
    fake_messages_query.insert.return_value.execute.return_value = SimpleNamespace(
        data=inserted_rows
    )
    fake_client.table.side_effect = lambda name: (
        fake_conversations_query if name == "ai_conversations" else fake_messages_query
    )
    return fake_client, fake_conversations_query, fake_messages_query


def test_append_messages_not_found_returns_404_and_does_not_insert(mocker):
    fake_client, _, fake_messages_query = _fake_client_for_append(mocker, None, [])
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.post(
        f"/ai/conversations/{MISSING_CONVERSATION_ID}/messages",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 404
    fake_messages_query.insert.assert_not_called()


def test_append_messages_inserts_and_touches_conversation(mocker):
    fake_client, fake_conversations_query, fake_messages_query = (
        _fake_client_for_append(mocker, {"id": CONVERSATION_ID}, [MESSAGE_ROW])
    )
    mocker.patch("app.routers.ai_conversations.user_client", return_value=fake_client)

    response = client.post(
        f"/ai/conversations/{CONVERSATION_ID}/messages",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 201
    assert response.json()["messages"][0]["id"] == "msg-1"
    inserted_rows = fake_messages_query.insert.call_args[0][0]
    assert inserted_rows == [
        {
            "conversation_id": CONVERSATION_ID,
            "user_id": "user-1",
            "payload": {"role": "user", "content": "hi"},
        }
    ]
    fake_conversations_query.update.assert_called_once()


class TestConversationsAuth:
    def test_list_requires_bearer_token(self):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            response = client.get("/ai/conversations")
            assert response.status_code == 401
        finally:
            app.dependency_overrides[get_current_user] = override_current_user
