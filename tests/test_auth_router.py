from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.permissions import RoleId
from app.routers import auth

app = FastAPI()
app.include_router(auth.router)
client = TestClient(app)


def _fake_admin_client(*, profile_data=None, known_login_data=None):
    """admin_client() is queried against 2 different tables inside
    login()/refresh() (profiles, known_logins). .table() needs a side_effect
    keyed by table name so each table gets its own independently-configured
    mock chain instead of colliding on a shared .table.return_value."""
    fake_profiles = MagicMock()
    fake_profiles.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=profile_data) if profile_data is not None else None
    )

    fake_known_logins = MagicMock()
    fake_known_logins.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        SimpleNamespace(data=known_login_data) if known_login_data is not None else None
    )

    fake_admin = MagicMock()
    tables = {
        "profiles": fake_profiles,
        "known_logins": fake_known_logins,
    }
    fake_admin.table.side_effect = lambda name: tables[name]
    return fake_admin, fake_profiles, fake_known_logins


MEMBER_PROFILE = {
    "roles": {"name": "member"},
    "membership_tier": "regular",
    "deleted_at": None,
}
ADMIN_PROFILE = {
    "roles": {"name": "admin"},
    "membership_tier": None,
    "deleted_at": None,
}
SUPER_ADMIN_PROFILE = {
    "roles": {"name": "super_admin"},
    "membership_tier": None,
    "deleted_at": None,
}


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

    fake_admin, _, _ = _fake_admin_client(profile_data=MEMBER_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login", json={"email": "a@b.com", "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "token": "access-tok",
        "refreshToken": "refresh-tok",
        "user": {
            "id": "user-1",
            "email": "a@b.com",
            "role": "member",
            "membershipTier": "regular",
        },
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


def test_login_no_profile_row_defaults_to_member(mocker):
    """Defends against a race/edge case (login before the profile insert from
    register() has landed) — must not crash, must default to the least-privileged role.
    """
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, _, _ = _fake_admin_client(profile_data=None)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login", json={"email": "a@b.com", "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "member"
    assert response.json()["user"]["membershipTier"] is None


def test_login_soft_deleted_account_returns_403(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, _, _ = _fake_admin_client(
        profile_data={
            "role": "member",
            "membership_tier": "regular",
            "deleted_at": "2026-08-14T00:00:00Z",
        }
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login", json={"email": "a@b.com", "password": "password123"}
    )

    assert response.status_code == 403


def test_login_promotes_initial_admin_email(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="boss@srwiki.dev"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, fake_profiles, _ = _fake_admin_client(profile_data=MEMBER_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")
    fake_settings = mocker.MagicMock(initial_admin_email="boss@srwiki.dev")
    mocker.patch("app.routers.auth.get_settings", return_value=fake_settings)

    response = client.post(
        "/auth/login", json={"email": "boss@srwiki.dev", "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "super_admin"
    update_call = fake_profiles.update.call_args[0][0]
    assert update_call == {"role_id": RoleId.SUPER_ADMIN}


def test_login_non_matching_email_does_not_promote(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, fake_profiles, _ = _fake_admin_client(profile_data=MEMBER_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")
    fake_settings = mocker.MagicMock(initial_admin_email="boss@srwiki.dev")
    mocker.patch("app.routers.auth.get_settings", return_value=fake_settings)

    response = client.post(
        "/auth/login", json={"email": "a@b.com", "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "member"
    fake_profiles.update.assert_not_called()


def test_login_already_super_admin_does_not_reissue_update(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="boss@srwiki.dev"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, fake_profiles, _ = _fake_admin_client(profile_data=SUPER_ADMIN_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")
    fake_settings = mocker.MagicMock(initial_admin_email="boss@srwiki.dev")
    mocker.patch("app.routers.auth.get_settings", return_value=fake_settings)

    response = client.post(
        "/auth/login", json={"email": "boss@srwiki.dev", "password": "password123"}
    )

    assert response.status_code == 200
    fake_profiles.update.assert_not_called()


def test_login_plain_admin_still_gets_promoted_to_super_admin(mocker):
    """The bootstrap email is the root of the system — even a user who is
    already a plain 'admin' (e.g. promoted separately) must still become
    super_admin on next login, since only role == 'super_admin' skips it."""
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="boss@srwiki.dev"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, fake_profiles, _ = _fake_admin_client(profile_data=ADMIN_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")
    fake_settings = mocker.MagicMock(initial_admin_email="boss@srwiki.dev")
    mocker.patch("app.routers.auth.get_settings", return_value=fake_settings)

    response = client.post(
        "/auth/login", json={"email": "boss@srwiki.dev", "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "super_admin"
    update_call = fake_profiles.update.call_args[0][0]
    assert update_call == {"role_id": RoleId.SUPER_ADMIN}


def test_login_new_device_creates_known_login_and_notification(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, _, fake_known_logins = _fake_admin_client(profile_data=MEMBER_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mock_create_notification = mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"x-forwarded-for": "1.2.3.4", "user-agent": "TestAgent/1.0"},
    )

    assert response.status_code == 200
    insert_call = fake_known_logins.insert.call_args[0][0]
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

    fake_admin, _, fake_known_logins = _fake_admin_client(profile_data=MEMBER_PROFILE)
    fake_known_logins.insert.return_value.execute.side_effect = APIError(
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
    update_call = fake_known_logins.update.call_args[0][0]
    assert "last_seen_at" in update_call
    mock_create_notification.assert_not_called()


def test_login_new_device_insert_unrelated_failure_does_not_break_login(mocker):
    """An insert failure that is NOT the (user_id, device_hash) unique violation
    is a device-tracking side effect, not the login itself — must be logged and
    swallowed rather than surfacing as a 500 for a login that already succeeded."""
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, _, fake_known_logins = _fake_admin_client(profile_data=MEMBER_PROFILE)
    fake_known_logins.insert.return_value.execute.side_effect = APIError(
        {"code": "42501", "message": "permission denied for table known_logins"}
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mock_create_notification = mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"x-forwarded-for": "1.2.3.4", "user-agent": "TestAgent/1.0"},
    )

    assert response.status_code == 200
    fake_known_logins.update.assert_not_called()
    mock_create_notification.assert_not_called()


def test_login_track_device_failure_does_not_break_login(mocker):
    """If the notification subsystem/known_logins table is unavailable, login()
    must still return its normal 200 response — only the best-effort
    device-tracking side effect may fail."""
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)
    fake_admin, _, _ = _fake_admin_client(profile_data=MEMBER_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch(
        "app.routers.auth._track_login_device",
        side_effect=Exception('relation "known_logins" does not exist'),
    )

    response = client.post(
        "/auth/login", json={"email": "a@b.com", "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json()["token"] == "access-tok"


def test_login_known_device_updates_last_seen_without_notification(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, _, fake_known_logins = _fake_admin_client(
        profile_data=MEMBER_PROFILE, known_login_data={"id": "kl-1"}
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mock_create_notification = mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"x-forwarded-for": "1.2.3.4", "user-agent": "TestAgent/1.0"},
    )

    assert response.status_code == 200
    fake_known_logins.insert.assert_not_called()
    update_call = fake_known_logins.update.call_args[0][0]
    assert "last_seen_at" in update_call
    mock_create_notification.assert_not_called()


def test_login_malformed_forwarded_for_falls_back_to_unknown_ip(mocker):
    """x-forwarded-for is fully client-controlled. A value that doesn't parse
    as a valid IP must not be stored/displayed verbatim."""
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, _, fake_known_logins = _fake_admin_client(profile_data=MEMBER_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mock_create_notification = mocker.patch("app.routers.auth.create_notification")

    response = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={
            "x-forwarded-for": "<script>not-an-ip</script>",
            "user-agent": "TestAgent/1.0",
        },
    )

    assert response.status_code == 200
    insert_call = fake_known_logins.insert.call_args[0][0]
    assert insert_call["ip_address"] == "unknown"
    call_kwargs = mock_create_notification.call_args
    assert "unknown" in call_kwargs[0][3]
    assert call_kwargs[1]["metadata"]["ip"] == "unknown"


def test_login_oversized_user_agent_gets_truncated(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    fake_admin, _, fake_known_logins = _fake_admin_client(profile_data=MEMBER_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)
    mocker.patch("app.routers.auth.create_notification")

    oversized_agent = "A" * 10_000
    response = client.post(
        "/auth/login",
        json={"email": "a@b.com", "password": "password123"},
        headers={"x-forwarded-for": "1.2.3.4", "user-agent": oversized_agent},
    )

    assert response.status_code == 200
    insert_call = fake_known_logins.insert.call_args[0][0]
    assert len(insert_call["user_agent"]) == auth.MAX_USER_AGENT_LENGTH


def test_refresh_success(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.refresh_session.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="new-access", refresh_token="new-refresh"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)
    fake_admin, _, _ = _fake_admin_client(profile_data=MEMBER_PROFILE)
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)

    response = client.post("/auth/refresh", json={"refreshToken": "old-refresh"})

    assert response.status_code == 200
    assert response.json()["token"] == "new-access"
    assert response.json()["user"]["role"] == "member"


def test_refresh_invalid_token_returns_401(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.refresh_session.side_effect = Exception("invalid refresh token")
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    response = client.post("/auth/refresh", json={"refreshToken": "bad"})

    assert response.status_code == 401


def test_refresh_soft_deleted_account_returns_403(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.refresh_session.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="new-access", refresh_token="new-refresh"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)
    fake_admin, _, _ = _fake_admin_client(
        profile_data={
            "role": "member",
            "membership_tier": "regular",
            "deleted_at": "2026-08-14T00:00:00Z",
        }
    )
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)

    response = client.post("/auth/refresh", json={"refreshToken": "old-refresh"})

    assert response.status_code == 403


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
