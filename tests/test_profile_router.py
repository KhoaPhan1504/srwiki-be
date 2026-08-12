import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.routers import profile

app = FastAPI()
app.include_router(profile.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)

PROFILE_ROW = {
    "id": "user-1",
    "full_name": "A B",
    "phone": None,
    "phone_verified": False,
    "address": None,
    "date_of_birth": None,
    "created_at": "2026-08-05T00:00:00Z",
    "updated_at": "2026-08-05T00:00:00Z",
}


def test_get_profile_success(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=PROFILE_ROW
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.get("/profile")

    assert response.status_code == 200
    assert response.json()["email"] == "a@b.com"
    assert response.json()["fullName"] == "A B"


def test_get_profile_not_found(mocker):
    fake_client = mocker.MagicMock()
    # postgrest-py returns None itself (not a response object) for zero rows.
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.get("/profile")

    assert response.status_code == 404


def test_update_profile_sends_only_provided_fields(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "full_name": "New Name"}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.put("/profile", json={"fullName": "New Name"})

    assert response.status_code == 200
    update_call = fake_client.table.return_value.update.call_args[0][0]
    assert update_call["full_name"] == "New Name"
    assert "address" not in update_call
    assert "phone" not in update_call


def test_update_profile_sends_json_serializable_date_of_birth(mocker):
    # Regression: payload.model_dump() without mode="json" used to leave
    # date_of_birth as a datetime.date object, which postgrest-py's httpx
    # transport can't JSON-encode, causing an unhandled 500 on every update
    # that included a dateOfBirth.
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "date_of_birth": "2002-04-15"}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.put("/profile", json={"dateOfBirth": "2002-04-15"})

    assert response.status_code == 200
    update_call = fake_client.table.return_value.update.call_args[0][0]
    assert update_call["date_of_birth"] == "2002-04-15"
    json.dumps(update_call)  # must not raise TypeError


def test_update_profile_rejects_phone_field():
    response = client.put("/profile", json={"phone": "+84912345678"})
    assert response.status_code == 422


def test_send_otp_invalid_phone_returns_422():
    response = client.post("/profile/phone/send-otp", json={"phone": "not-a-phone"})
    assert response.status_code == 422


def test_send_otp_success_returns_debug_code_in_debug_mode(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)
    fake_settings = mocker.MagicMock(otp_debug_mode=True)
    mocker.patch("app.routers.profile.get_settings", return_value=fake_settings)

    response = client.post("/profile/phone/send-otp", json={"phone": "+84912345678"})

    assert response.status_code == 200
    assert "debugOtp" in response.json()
    fake_admin.table.return_value.insert.assert_called_once()


def test_send_otp_omits_debug_code_when_debug_mode_off(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)
    fake_settings = mocker.MagicMock(otp_debug_mode=False)
    mocker.patch("app.routers.profile.get_settings", return_value=fake_settings)

    response = client.post("/profile/phone/send-otp", json={"phone": "+84912345678"})

    assert response.status_code == 200
    assert "debugOtp" not in response.json()


def test_verify_otp_success(mocker):
    fake_admin = mocker.MagicMock()
    query = (
        fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
    )
    query.execute.return_value = SimpleNamespace(data=[{"id": "otp-1"}])
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    fake_user_client = mocker.MagicMock()
    fake_user_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "phone": "+84912345678", "phone_verified": True}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_user_client)
    mocker.patch("app.routers.profile.create_notification")

    response = client.post(
        "/profile/phone/verify-otp", json={"phone": "+84912345678", "code": "123456"}
    )

    assert response.status_code == 200
    assert response.json()["phoneVerified"] is True


def test_verify_otp_invalid_code_returns_400(mocker):
    fake_admin = mocker.MagicMock()
    query = (
        fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
    )
    query.execute.return_value = SimpleNamespace(data=[])
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    response = client.post(
        "/profile/phone/verify-otp", json={"phone": "+84912345678", "code": "000000"}
    )

    assert response.status_code == 400


def test_delete_profile_calls_admin_delete_user(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    response = client.delete("/profile")

    assert response.status_code == 204
    fake_admin.auth.admin.delete_user.assert_called_once_with("user-1")


def test_upload_avatar_success(mocker):
    fake_client = mocker.MagicMock()
    fake_client.storage.from_.return_value.get_public_url.return_value = (
        "https://example.supabase.co/storage/v1/object/public/avatars/user-1/avatar"
    )
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "avatar_url": "https://example.supabase.co/.../avatar"}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)
    mocker.patch("app.routers.profile.create_notification")

    response = client.post(
        "/profile/avatar",
        files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["avatarUrl"]
    fake_client.storage.from_.return_value.upload.assert_called_once()
    upload_args = fake_client.storage.from_.return_value.upload.call_args
    assert upload_args[0][0] == "user-1/avatar"
    assert upload_args[0][2] == {"content-type": "image/png", "upsert": "true"}


def test_upload_avatar_rejects_invalid_content_type():
    response = client.post(
        "/profile/avatar",
        files={"file": ("avatar.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 422


def test_upload_avatar_rejects_oversized_file():
    oversized = b"x" * (2 * 1024 * 1024 + 1)
    response = client.post(
        "/profile/avatar",
        files={"file": ("avatar.png", oversized, "image/png")},
    )
    assert response.status_code == 422


def test_verify_otp_success_creates_notification(mocker):
    fake_admin = mocker.MagicMock()
    query = (
        fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
    )
    query.execute.return_value = SimpleNamespace(data=[{"id": "otp-1"}])
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    fake_user_client = mocker.MagicMock()
    fake_user_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "phone": "+84912345678", "phone_verified": True}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_user_client)
    mock_create_notification = mocker.patch("app.routers.profile.create_notification")

    response = client.post(
        "/profile/phone/verify-otp", json={"phone": "+84912345678", "code": "123456"}
    )

    assert response.status_code == 200
    mock_create_notification.assert_called_once()
    args = mock_create_notification.call_args[0]
    assert args[0] == "user-1"
    assert args[1] == "phone_verified"


def test_upload_avatar_success_creates_notification(mocker):
    fake_client = mocker.MagicMock()
    fake_client.storage.from_.return_value.get_public_url.return_value = (
        "https://example.supabase.co/storage/v1/object/public/avatars/user-1/avatar"
    )
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "avatar_url": "https://example.supabase.co/.../avatar"}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)
    mock_create_notification = mocker.patch("app.routers.profile.create_notification")

    response = client.post(
        "/profile/avatar",
        files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 200
    mock_create_notification.assert_called_once()
    args = mock_create_notification.call_args[0]
    assert args[0] == "user-1"
    assert args[1] == "avatar_updated"


def test_verify_otp_succeeds_even_if_notification_fails(mocker):
    """Fix 1: the phone was already verified (otp consumed, profile updated)
    before create_notification runs. If the notifications table/subsystem is
    unavailable, the client must still get its normal success response
    instead of an unhandled 500 that makes it look like verification failed
    (which would be worse: the caller can't just retry with the same code,
    since it's already been marked consumed)."""
    fake_admin = mocker.MagicMock()
    query = (
        fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
    )
    query.execute.return_value = SimpleNamespace(data=[{"id": "otp-1"}])
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    fake_user_client = mocker.MagicMock()
    fake_user_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "phone": "+84912345678", "phone_verified": True}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_user_client)
    mocker.patch(
        "app.routers.profile.create_notification",
        side_effect=Exception('relation "notifications" does not exist'),
    )

    response = client.post(
        "/profile/phone/verify-otp", json={"phone": "+84912345678", "code": "123456"}
    )

    assert response.status_code == 200
    assert response.json()["phoneVerified"] is True


def test_upload_avatar_succeeds_even_if_notification_fails(mocker):
    """Fix 1: the avatar was already uploaded and the profile row updated
    before create_notification runs — a notification-subsystem failure must
    not turn an otherwise-successful upload into a 500."""
    fake_client = mocker.MagicMock()
    fake_client.storage.from_.return_value.get_public_url.return_value = (
        "https://example.supabase.co/storage/v1/object/public/avatars/user-1/avatar"
    )
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "avatar_url": "https://example.supabase.co/.../avatar"}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)
    mocker.patch(
        "app.routers.profile.create_notification",
        side_effect=Exception('relation "notifications" does not exist'),
    )

    response = client.post(
        "/profile/avatar",
        files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["avatarUrl"]
