from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.routers import admin_members

app = FastAPI()
app.include_router(admin_members.router)


def override_current_user():
    return {"id": "admin-1", "email": "admin@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def _mock_role(mocker, role="admin", membership_tier=None, deleted_at=None):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    mock_admin.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={
            "role": role,
            "membership_tier": membership_tier,
            "deleted_at": deleted_at,
        }
    )
    return mock_admin


MEMBER_ROW = {
    "id": "member-1",
    "email": "member1@b.com",
    "full_name": "Member One",
    "role": "member",
    "membership_tier": "regular",
    "address": "123 Le Loi, Ha Noi",
    "date_of_birth": "1995-06-01",
    "created_at": "2026-08-01T00:00:00+00:00",
    "updated_at": "2026-08-01T00:00:00+00:00",
}


def test_list_members_rejects_non_admin(mocker):
    _mock_role(mocker, role="member")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.get("/admin/members")

    assert response.status_code == 403


def test_list_members_returns_paginated_results(mocker):
    _mock_role(mocker, role="admin")
    fake_admin = mocker.MagicMock()
    query = (
        fake_admin.table.return_value.select.return_value.eq.return_value.is_.return_value
    )
    query.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[MEMBER_ROW], count=1
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["pageSize"] == 20
    assert body["items"][0]["email"] == "member1@b.com"
    assert body["items"][0]["membershipTier"] == "regular"
    fake_admin.table.return_value.select.return_value.eq.assert_called_with(
        "role", "member"
    )


def test_list_members_returns_empty_list_when_no_rows(mocker):
    _mock_role(mocker, role="admin")
    fake_admin = mocker.MagicMock()
    query = (
        fake_admin.table.return_value.select.return_value.eq.return_value.is_.return_value
    )
    query.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_members_applies_pagination_params(mocker):
    _mock_role(mocker, role="admin")
    fake_admin = mocker.MagicMock()
    query = (
        fake_admin.table.return_value.select.return_value.eq.return_value.is_.return_value
    )
    query.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members?page=3&pageSize=10")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 3
    assert body["pageSize"] == 10
    query.order.return_value.range.assert_called_once_with(20, 29)
