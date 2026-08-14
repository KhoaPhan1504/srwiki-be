from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.permissions import RoleId
from app.routers import admin_admins

app = FastAPI()
app.include_router(admin_admins.router)


def override_current_user():
    return {"id": "super-admin-1", "email": "super@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def _mock_role(mocker, role="super_admin"):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    mock_admin.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={"roles": {"name": role}, "membership_tier": None, "deleted_at": None}
    )
    return mock_admin


def _fake_admin_client():
    """Role ids are fixed RoleId enum constants now (no more roles-table
    lookup), so admin_client() is only ever queried against profiles."""
    fake_profiles = MagicMock()
    fake_admin = MagicMock()
    fake_admin.table.side_effect = lambda name: {"profiles": fake_profiles}[name]
    return fake_admin, fake_profiles


ADMIN_ROW = {
    "id": "admin-2",
    "email": "admin2@b.com",
    "full_name": "Admin Two",
    "roles": {"name": "admin"},
    "membership_tier": None,
    "address": "1 Admin St",
    "date_of_birth": "1990-01-01",
    "created_at": "2026-08-01T00:00:00+00:00",
    "updated_at": "2026-08-01T00:00:00+00:00",
}


def test_list_admins_rejects_plain_member(mocker):
    _mock_role(mocker, role="member")
    mocker.patch("app.routers.admin_admins.admin_client")

    response = client.get("/admin/admins")

    assert response.status_code == 403


def test_list_admins_allows_plain_admin(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles = _fake_admin_client()
    query = fake_profiles.select.return_value.eq.return_value.is_.return_value
    query.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[ADMIN_ROW], count=1
    )
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.get("/admin/admins")

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["email"] == "admin2@b.com"
    assert body["items"][0]["role"] == "admin"
    fake_profiles.select.return_value.eq.assert_called_with("role_id", RoleId.ADMIN)


def test_list_admins_returns_empty_list(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles = _fake_admin_client()
    query = fake_profiles.select.return_value.eq.return_value.is_.return_value
    query.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.get("/admin/admins")

    assert response.status_code == 200
    assert response.json()["items"] == []


CREATE_PAYLOAD = {
    "email": "new-admin@b.com",
    "password": "password123",
    "fullName": "New Admin",
}


def test_create_admin_rejects_plain_admin(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_admins.admin_client")

    response = client.post("/admin/admins", json=CREATE_PAYLOAD)

    assert response.status_code == 403


def test_create_admin_success(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles = _fake_admin_client()
    fake_admin.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id="admin-2", email="new-admin@b.com")
    )
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=ADMIN_ROW
    )
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.post("/admin/admins", json=CREATE_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "admin"
    insert_call = fake_profiles.insert.call_args[0][0]
    assert insert_call["role_id"] == RoleId.ADMIN
    assert insert_call["membership_tier"] is None


def test_create_admin_rejects_role_field(mocker):
    _mock_role(mocker, role="super_admin")
    mocker.patch("app.routers.admin_admins.admin_client")
    payload = {**CREATE_PAYLOAD, "role": "super_admin"}

    response = client.post("/admin/admins", json=payload)

    assert response.status_code == 422


def test_update_admin_rejects_plain_admin(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_admins.admin_client")

    response = client.put("/admin/admins/admin-2", json={"fullName": "New Name"})

    assert response.status_code == 403


def test_update_admin_not_found_returns_404(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles = _fake_admin_client()
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.put("/admin/admins/missing", json={"fullName": "New Name"})

    assert response.status_code == 404


def test_update_admin_success(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles = _fake_admin_client()
    fetch_execute = (
        fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute
    )
    fetch_execute.side_effect = [
        SimpleNamespace(data=ADMIN_ROW),
        SimpleNamespace(data={**ADMIN_ROW, "full_name": "Updated Name"}),
    ]
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.put("/admin/admins/admin-2", json={"fullName": "Updated Name"})

    assert response.status_code == 200
    assert response.json()["fullName"] == "Updated Name"
    update_call = fake_profiles.update.call_args[0][0]
    assert update_call == {"full_name": "Updated Name"}


def test_delete_admin_rejects_plain_admin(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_admins.admin_client")

    response = client.delete("/admin/admins/admin-2")

    assert response.status_code == 403


def test_delete_admin_not_found_returns_404(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles = _fake_admin_client()
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.delete("/admin/admins/missing")

    assert response.status_code == 404


def test_delete_admin_success_soft_deletes(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles = _fake_admin_client()
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=ADMIN_ROW
    )
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.delete("/admin/admins/admin-2")

    assert response.status_code == 204
    update_call = fake_profiles.update.call_args[0][0]
    assert "deleted_at" in update_call


def test_demote_admin_rejects_plain_admin(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_admins.admin_client")

    response = client.post("/admin/admins/admin-2/demote")

    assert response.status_code == 403


def test_demote_admin_not_found_returns_404(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles = _fake_admin_client()
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.post("/admin/admins/missing/demote")

    assert response.status_code == 404


def test_demote_admin_success(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles = _fake_admin_client()
    fetch_with_role_filter = (
        fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute
    )
    fetch_with_role_filter.return_value = SimpleNamespace(data=ADMIN_ROW)
    fetch_by_id_only = (
        fake_profiles.select.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute
    )
    fetch_by_id_only.return_value = SimpleNamespace(
        data={**ADMIN_ROW, "roles": {"name": "member"}, "membership_tier": "regular"}
    )
    mocker.patch("app.routers.admin_admins.admin_client", return_value=fake_admin)

    response = client.post("/admin/admins/admin-2/demote")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "member"
    assert body["membershipTier"] == "regular"
    update_call = fake_profiles.update.call_args[0][0]
    assert update_call == {"role_id": RoleId.MEMBER, "membership_tier": "regular"}
