from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import profile
from app.dependencies import get_current_user

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
    assert response.json()["full_name"] == "A B"


def test_get_profile_not_found(mocker):
    fake_client = mocker.MagicMock()
    # postgrest-py returns None itself (not a response object) for zero rows.
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = None
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.get("/profile")

    assert response.status_code == 404


def test_update_profile_sends_only_provided_fields(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "full_name": "New Name"}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.put("/profile", json={"full_name": "New Name"})

    assert response.status_code == 200
    update_call = fake_client.table.return_value.update.call_args[0][0]
    assert update_call["full_name"] == "New Name"
    assert "address" not in update_call
    assert "phone" not in update_call


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
    assert "debug_otp" in response.json()
    fake_admin.table.return_value.insert.assert_called_once()


def test_send_otp_omits_debug_code_when_debug_mode_off(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)
    fake_settings = mocker.MagicMock(otp_debug_mode=False)
    mocker.patch("app.routers.profile.get_settings", return_value=fake_settings)

    response = client.post("/profile/phone/send-otp", json={"phone": "+84912345678"})

    assert response.status_code == 200
    assert "debug_otp" not in response.json()


def test_verify_otp_success(mocker):
    fake_admin = mocker.MagicMock()
    query = fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
    query.execute.return_value = SimpleNamespace(data=[{"id": "otp-1"}])
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    fake_user_client = mocker.MagicMock()
    fake_user_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "phone": "+84912345678", "phone_verified": True}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_user_client)

    response = client.post(
        "/profile/phone/verify-otp", json={"phone": "+84912345678", "code": "123456"}
    )

    assert response.status_code == 200
    assert response.json()["phone_verified"] is True


def test_verify_otp_invalid_code_returns_400(mocker):
    fake_admin = mocker.MagicMock()
    query = fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
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
