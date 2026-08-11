from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.routers import auth

app = FastAPI()
app.include_router(auth.router)
client = TestClient(app)


def test_register_success(mocker):
    fake_anon = mocker.MagicMock()
    fake_anon.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-1", email="a@b.com", identities=[{"id": "ident-1"}]
        ),
        session=None,
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_anon)
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)

    response = client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "password123", "fullName": "A B"},
    )

    assert response.status_code == 201
    assert response.json() == {"id": "user-1", "email": "a@b.com"}
    fake_admin.table.return_value.insert.assert_called_once_with(
        {"id": "user-1", "full_name": "A B"}
    )


def test_register_rolls_back_user_when_profile_insert_fails(mocker):
    fake_anon = mocker.MagicMock()
    fake_anon.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="user-1", email="a@b.com", identities=[{"id": "ident-1"}]
        ),
        session=None,
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_anon)
    fake_admin = mocker.MagicMock()
    fake_admin.table.return_value.insert.return_value.execute.side_effect = Exception(
        "db error"
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)

    response = client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "password123", "fullName": "A B"},
    )

    assert response.status_code == 500
    fake_admin.auth.admin.delete_user.assert_called_once_with("user-1")


def test_register_existing_email_returns_409_without_touching_admin(mocker):
    """GoTrue's anti-enumeration protection returns a fake user with no identities."""
    fake_anon = mocker.MagicMock()
    fake_anon.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com", identities=[]), session=None
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_anon)
    mock_admin = mocker.patch("app.routers.auth.admin_client")

    response = client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "password123", "fullName": "A B"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"
    mock_admin.assert_not_called()


def test_register_failure_returns_400_without_leaking_exception(mocker):
    fake_anon = mocker.MagicMock()
    fake_anon.auth.sign_up.side_effect = Exception("secret internal supabase error")
    mocker.patch("app.routers.auth.anon_client", return_value=fake_anon)

    response = client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "password123", "fullName": "A B"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Registration failed"
    assert "secret internal supabase error" not in response.text


def test_login_success(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin = mocker.MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login", json={"email": "a@b.com", "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "token": "access-tok",
        "refreshToken": "refresh-tok",
        "user": {"id": "user-1", "email": "a@b.com"},
    }


def test_login_invalid_credentials_returns_401(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.side_effect = Exception(
        "Invalid login credentials"
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    response = client.post(
        "/auth/login", json={"email": "a@b.com", "password": "wrong"}
    )

    assert response.status_code == 401


def test_login_new_device_creates_known_login_and_notification(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin = mocker.MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mock_create_notification = mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"x-forwarded-for": "1.2.3.4", "user-agent": "TestAgent/1.0"},
    )

    assert response.status_code == 200
    insert_call = fake_admin.table.return_value.insert.call_args[0][0]
    assert insert_call["user_id"] == "user-1"
    assert insert_call["ip_address"] == "1.2.3.4"
    assert insert_call["user_agent"] == "TestAgent/1.0"
    mock_create_notification.assert_called_once()
    call_args = mock_create_notification.call_args[0]
    assert call_args[0] == "user-1"
    assert call_args[1] == "new_device_login"


def test_login_new_device_insert_race_falls_back_to_update_without_notification(mocker):
    """Two concurrent logins from the same new device both see 'no existing row',
    but only one insert wins the unique (user_id, device_hash) constraint. The
    loser must not surface a 500 — it should fall back to an update and skip
    the notification (the winner sends it)."""
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin = mocker.MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    fake_admin.table.return_value.insert.return_value.execute.side_effect = APIError(
        {
            "code": "23505",
            "message": 'duplicate key value violates unique constraint "known_logins_user_id_device_hash_key"',
        }
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mock_create_notification = mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"x-forwarded-for": "1.2.3.4", "user-agent": "TestAgent/1.0"},
    )

    assert response.status_code == 200
    update_call = fake_admin.table.return_value.update.call_args[0][0]
    assert "last_seen_at" in update_call
    mock_create_notification.assert_not_called()


def test_login_new_device_insert_unrelated_failure_propagates(mocker):
    """An insert failure that is NOT the (user_id, device_hash) unique violation
    (e.g. a bad service-role key, network blip, schema drift) must not be
    silently swallowed as if it were the race — it should propagate so the
    caller sees a loud failure instead of a fake 200 with no row written."""
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin = mocker.MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    fake_admin.table.return_value.insert.return_value.execute.side_effect = APIError(
        {"code": "42501", "message": "permission denied for table known_logins"}
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mock_create_notification = mocker.patch("app.routers.auth.create_notification")

    with pytest.raises(APIError):
        client.post(
            "/auth/login",
            json={"email": "a@b.com", "password": "password123"},
            headers={"x-forwarded-for": "1.2.3.4", "user-agent": "TestAgent/1.0"},
        )

    fake_admin.table.return_value.update.assert_not_called()
    mock_create_notification.assert_not_called()


def test_login_known_device_updates_last_seen_without_notification(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin = mocker.MagicMock()
    fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={"id": "kl-1"}
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mock_create_notification = mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"x-forwarded-for": "1.2.3.4", "user-agent": "TestAgent/1.0"},
    )

    assert response.status_code == 200
    fake_admin.table.return_value.insert.assert_not_called()
    update_call = fake_admin.table.return_value.update.call_args[0][0]
    assert "last_seen_at" in update_call
    mock_create_notification.assert_not_called()


def test_refresh_success(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.refresh_session.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="new-access", refresh_token="new-refresh"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    response = client.post("/auth/refresh", json={"refreshToken": "old-refresh"})

    assert response.status_code == 200
    assert response.json()["token"] == "new-access"


def test_refresh_invalid_token_returns_401(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.refresh_session.side_effect = Exception("invalid refresh token")
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    response = client.post("/auth/refresh", json={"refreshToken": "bad"})

    assert response.status_code == 401


def test_logout_requires_auth():
    response = client.post("/auth/logout")
    assert response.status_code == 401


def test_logout_success_with_valid_token(mocker):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    fake_user = SimpleNamespace(id="user-1", email="a@b.com")
    mock_admin.return_value.auth.get_user.return_value = SimpleNamespace(user=fake_user)

    response = client.post(
        "/auth/logout", headers={"Authorization": "Bearer good-token"}
    )

    assert response.status_code == 204
