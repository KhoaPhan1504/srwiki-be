from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.routers import settings

app = FastAPI()
app.include_router(settings.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def test_get_settings_returns_defaults_when_no_row(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.settings.user_client", return_value=fake_client)

    response = client.get("/settings")

    assert response.status_code == 200
    assert response.json() == {
        "language": "vi",
        "timezone": "Asia/Ho_Chi_Minh",
        "theme": "system",
        "emailNotifications": True,
    }


def test_get_settings_returns_stored_values(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={"settings": {"language": "en", "theme": "dark"}}
    )
    mocker.patch("app.routers.settings.user_client", return_value=fake_client)

    response = client.get("/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "en"
    assert body["theme"] == "dark"
    assert body["timezone"] == "Asia/Ho_Chi_Minh"
    assert body["emailNotifications"] is True


def test_update_settings_merges_partial_payload(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={"settings": {"language": "en", "theme": "dark"}}
    )
    mocker.patch("app.routers.settings.user_client", return_value=fake_client)
    mocker.patch("app.routers.settings.create_notification")

    response = client.put("/settings", json={"theme": "light"})

    assert response.status_code == 200
    body = response.json()
    assert body["theme"] == "light"
    assert body["language"] == "en"  # untouched field preserved, not reset to default

    upsert_call = fake_client.table.return_value.upsert.call_args[0][0]
    assert upsert_call["settings"] == {"language": "en", "theme": "light"}
    assert upsert_call["user_id"] == "user-1"


def test_update_settings_rejects_invalid_theme():
    response = client.put("/settings", json={"theme": "purple"})
    assert response.status_code == 422


def test_update_settings_creates_notification_when_payload_nonempty(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={"settings": {"language": "en"}}
    )
    mocker.patch("app.routers.settings.user_client", return_value=fake_client)
    mock_create_notification = mocker.patch("app.routers.settings.create_notification")

    response = client.put("/settings", json={"theme": "dark"})

    assert response.status_code == 200
    mock_create_notification.assert_called_once()
    args = mock_create_notification.call_args[0]
    assert args[0] == "user-1"
    assert args[1] == "settings_updated"


def test_update_settings_no_notification_when_payload_empty(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={"settings": {"language": "en"}}
    )
    mocker.patch("app.routers.settings.user_client", return_value=fake_client)
    mock_create_notification = mocker.patch("app.routers.settings.create_notification")

    response = client.put("/settings", json={})

    assert response.status_code == 200
    mock_create_notification.assert_not_called()
