from types import SimpleNamespace
from unittest.mock import MagicMock

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
            "roles": {"name": role},
            "membership_tier": membership_tier,
            "deleted_at": deleted_at,
        }
    )
    return mock_admin


MEMBER_ROLE_ID = "role-member-id"
ADMIN_ROLE_ID = "role-admin-id"


def _fake_admin_client():
    """admin_client() is queried against 2 different tables inside these
    endpoints (profiles, roles). get_role_id() is called with different role
    names within the same request (promote_member needs both 'member' and
    'admin'), so the roles mock resolves per the queried name instead of
    returning one fixed id. .table() needs a side_effect keyed by table name
    so each table gets its own independently-configured mock chain instead
    of colliding on a shared .table.return_value."""
    fake_profiles = MagicMock()

    fake_roles = MagicMock()

    def _eq_side_effect(_column, role_name):
        role_id = {"admin": ADMIN_ROLE_ID, "member": MEMBER_ROLE_ID}[role_name]
        eq_result = MagicMock()
        eq_result.maybe_single.return_value.execute.return_value = SimpleNamespace(
            data={"id": role_id}
        )
        return eq_result

    fake_roles.select.return_value.eq.side_effect = _eq_side_effect

    fake_admin = MagicMock()
    tables = {"profiles": fake_profiles, "roles": fake_roles}
    fake_admin.table.side_effect = lambda name: tables[name]
    return fake_admin, fake_profiles, fake_roles


MEMBER_ROW = {
    "id": "member-1",
    "email": "member1@b.com",
    "full_name": "Member One",
    "roles": {"name": "member"},
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
    fake_admin, fake_profiles, _ = _fake_admin_client()
    query = fake_profiles.select.return_value.eq.return_value.is_.return_value
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
    fake_profiles.select.return_value.eq.assert_called_with("role_id", MEMBER_ROLE_ID)


def test_list_members_returns_empty_list_when_no_rows(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    query = fake_profiles.select.return_value.eq.return_value.is_.return_value
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
    fake_admin, fake_profiles, _ = _fake_admin_client()
    query = fake_profiles.select.return_value.eq.return_value.is_.return_value
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


def test_list_members_no_filter_skips_in_call(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    query = fake_profiles.select.return_value.eq.return_value.is_.return_value
    query.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members")

    assert response.status_code == 200
    query.in_.assert_not_called()


def test_list_members_filters_by_single_membership_tier(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    base = fake_profiles.select.return_value.eq.return_value.is_.return_value
    base.in_.return_value.order.return_value.range.return_value.execute.return_value = (
        SimpleNamespace(data=[], count=0)
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members?membershipTier=vip")

    assert response.status_code == 200
    assert base.in_.call_args[0] == ("membership_tier", ["vip"])


def test_list_members_filters_by_both_membership_tiers(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    base = fake_profiles.select.return_value.eq.return_value.is_.return_value
    base.in_.return_value.order.return_value.range.return_value.execute.return_value = (
        SimpleNamespace(data=[], count=0)
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members?membershipTier=regular,vip")

    assert response.status_code == 200
    assert base.in_.call_args[0] == ("membership_tier", ["regular", "vip"])


def test_list_members_filters_created_at_range(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    base = fake_profiles.select.return_value.eq.return_value.is_.return_value
    base.gte.return_value.lt.return_value.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get(
        "/admin/members?createdAtFrom=2026-01-01T00:00:00Z&createdAtTo=2026-08-15T00:00:00Z"
    )

    assert response.status_code == 200
    assert base.gte.call_args[0][0] == "created_at"
    assert base.gte.return_value.lt.call_args[0][0] == "created_at"


def test_list_members_filters_address_contains(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    base = fake_profiles.select.return_value.eq.return_value.is_.return_value
    base.ilike.return_value.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members?address=Ha+Noi")

    assert response.status_code == 200
    assert base.ilike.call_args[0] == ("address", "%Ha Noi%")


def test_list_members_filters_birthday_range(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    base = fake_profiles.select.return_value.eq.return_value.is_.return_value
    base.gte.return_value.lte.return_value.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get(
        "/admin/members?birthdayFrom=1990-01-01&birthdayTo=2000-12-31"
    )

    assert response.status_code == 200
    assert base.gte.call_args[0][0] == "date_of_birth"
    assert base.gte.return_value.lte.call_args[0][0] == "date_of_birth"


def test_list_members_invalid_birthday_range_returns_400(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.get(
        "/admin/members?birthdayFrom=2000-01-01&birthdayTo=1990-01-01"
    )

    assert response.status_code == 400


def test_list_members_invalid_created_at_range_returns_400(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.get(
        "/admin/members?createdAtFrom=2026-08-15T00:00:00Z&createdAtTo=2026-01-01T00:00:00Z"
    )

    assert response.status_code == 400


def test_list_members_combines_filters_with_and(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    base = fake_profiles.select.return_value.eq.return_value.is_.return_value
    base.in_.return_value.ilike.return_value.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members?membershipTier=vip&address=Ha+Noi")

    assert response.status_code == 200
    assert base.in_.call_args[0] == ("membership_tier", ["vip"])
    assert base.in_.return_value.ilike.call_args[0] == ("address", "%Ha Noi%")


CREATE_PAYLOAD = {
    "email": "new@member.com",
    "password": "password123",
    "fullName": "New Member",
    "address": "1 Test St",
    "dateOfBirth": "1998-03-10",
}

CREATED_ROW = {
    "id": "new-member-1",
    "email": "new@member.com",
    "full_name": "New Member",
    "roles": {"name": "member"},
    "membership_tier": "regular",
    "address": "1 Test St",
    "date_of_birth": "1998-03-10",
    "created_at": "2026-08-14T00:00:00+00:00",
    "updated_at": "2026-08-14T00:00:00+00:00",
}


def test_create_member_rejects_non_admin(mocker):
    _mock_role(mocker, role="member")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.post("/admin/members", json=CREATE_PAYLOAD)

    assert response.status_code == 403


def test_create_member_success(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fake_admin.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id="new-member-1", email="new@member.com")
    )
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=CREATED_ROW
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.post("/admin/members", json=CREATE_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "member"
    assert body["membershipTier"] == "regular"
    insert_call = fake_profiles.insert.call_args[0][0]
    assert insert_call["role_id"] == MEMBER_ROLE_ID
    assert insert_call["membership_tier"] == "regular"
    assert insert_call["id"] == "new-member-1"


def test_create_member_rejects_role_field(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_members.admin_client")
    payload = {**CREATE_PAYLOAD, "role": "admin"}

    response = client.post("/admin/members", json=payload)

    assert response.status_code == 422


def test_create_member_rejects_membership_tier_field(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_members.admin_client")
    payload = {**CREATE_PAYLOAD, "membershipTier": "vip"}

    response = client.post("/admin/members", json=payload)

    assert response.status_code == 422


def test_create_member_rolls_back_user_when_profile_insert_fails(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fake_admin.auth.admin.create_user.return_value = SimpleNamespace(
        user=SimpleNamespace(id="new-member-1", email="new@member.com")
    )
    fake_profiles.insert.return_value.execute.side_effect = Exception("db error")
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.post("/admin/members", json=CREATE_PAYLOAD)

    assert response.status_code == 500
    fake_admin.auth.admin.delete_user.assert_called_once_with("new-member-1")


def test_update_member_rejects_non_admin(mocker):
    _mock_role(mocker, role="member")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.put("/admin/members/member-1", json={"fullName": "New Name"})

    assert response.status_code == 403


def test_update_member_not_found_returns_404(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.put("/admin/members/missing", json={"fullName": "New Name"})

    assert response.status_code == 404


def test_update_member_success(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fetch_execute = (
        fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute
    )
    fetch_execute.side_effect = [
        SimpleNamespace(data=MEMBER_ROW),
        SimpleNamespace(data={**MEMBER_ROW, "membership_tier": "vip"}),
    ]
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.put("/admin/members/member-1", json={"membershipTier": "vip"})

    assert response.status_code == 200
    assert response.json()["membershipTier"] == "vip"
    update_call = fake_profiles.update.call_args[0][0]
    assert update_call == {"membership_tier": "vip"}


def test_update_member_rejects_role_field(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.put("/admin/members/member-1", json={"role": "admin"})

    assert response.status_code == 422


def test_update_member_no_changes_skips_update_call(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fetch_execute = (
        fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute
    )
    fetch_execute.return_value = SimpleNamespace(data=MEMBER_ROW)
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.put("/admin/members/member-1", json={})

    assert response.status_code == 200
    fake_profiles.update.assert_not_called()


def test_delete_member_rejects_non_admin(mocker):
    _mock_role(mocker, role="member")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.delete("/admin/members/member-1")

    assert response.status_code == 403


def test_delete_member_rejects_self_delete(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.delete("/admin/members/admin-1")

    assert response.status_code == 400


def test_delete_member_not_found_returns_404(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.delete("/admin/members/missing")

    assert response.status_code == 404


def test_delete_member_success_soft_deletes(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=MEMBER_ROW
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.delete("/admin/members/member-1")

    assert response.status_code == 204
    update_call = fake_profiles.update.call_args[0][0]
    assert "deleted_at" in update_call
    fake_admin.auth.admin.delete_user.assert_not_called()


def test_deleted_member_excluded_from_list(mocker):
    _mock_role(mocker, role="admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    query = fake_profiles.select.return_value.eq.return_value.is_.return_value
    query.order.return_value.range.return_value.execute.return_value = SimpleNamespace(
        data=[], count=0
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.get("/admin/members")

    assert response.status_code == 200
    assert response.json()["items"] == []
    fake_profiles.select.return_value.eq.return_value.is_.assert_called_with(
        "deleted_at", "null"
    )


def test_promote_member_rejects_plain_admin(mocker):
    _mock_role(mocker, role="admin")
    mocker.patch("app.routers.admin_members.admin_client")

    response = client.post("/admin/members/member-1/promote")

    assert response.status_code == 403


def test_promote_member_not_found_returns_404(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.post("/admin/members/missing/promote")

    assert response.status_code == 404


def test_promote_member_success(mocker):
    _mock_role(mocker, role="super_admin")
    fake_admin, fake_profiles, _ = _fake_admin_client()
    fetch_with_role_filter = (
        fake_profiles.select.return_value.eq.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute
    )
    fetch_with_role_filter.return_value = SimpleNamespace(data=MEMBER_ROW)
    fetch_by_id_only = (
        fake_profiles.select.return_value.eq.return_value.is_.return_value.maybe_single.return_value.execute
    )
    fetch_by_id_only.return_value = SimpleNamespace(
        data={**MEMBER_ROW, "roles": {"name": "admin"}, "membership_tier": None}
    )
    mocker.patch("app.routers.admin_members.admin_client", return_value=fake_admin)

    response = client.post("/admin/members/member-1/promote")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert "membershipTier" not in body
    update_call = fake_profiles.update.call_args[0][0]
    assert update_call == {"role_id": ADMIN_ROLE_ID, "membership_tier": None}
