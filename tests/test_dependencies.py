from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.dependencies import (
    get_current_user,
    get_current_user_with_role,
    require_permission,
)

app = FastAPI()


@app.get("/whoami")
def whoami(current_user: dict = Depends(get_current_user)):
    return current_user


client = TestClient(app)


def test_missing_authorization_header_returns_401():
    response = client.get("/whoami")
    assert response.status_code == 401


def test_invalid_token_returns_401(mocker):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    mock_admin.return_value.auth.get_user.side_effect = Exception("invalid jwt")

    response = client.get("/whoami", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401


def test_valid_token_returns_user(mocker):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    fake_user = SimpleNamespace(id="user-1", email="a@b.com")
    mock_admin.return_value.auth.get_user.return_value = SimpleNamespace(user=fake_user)

    response = client.get("/whoami", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    assert response.json() == {
        "id": "user-1",
        "email": "a@b.com",
        "access_token": "good-token",
    }


@app.get("/whoami-with-role")
def whoami_with_role(current_user: dict = Depends(get_current_user_with_role)):
    return current_user


require_members_read = require_permission("members.read")


@app.get("/members-only")
def members_only(current_user: dict = Depends(require_members_read)):
    return current_user


def _mock_profile(mocker, role="member", membership_tier=None, deleted_at=None):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    fake_user = SimpleNamespace(id="user-1", email="a@b.com")
    mock_admin.return_value.auth.get_user.return_value = SimpleNamespace(user=fake_user)
    mock_admin.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={
            "role": role,
            "membership_tier": membership_tier,
            "deleted_at": deleted_at,
        }
    )
    return mock_admin


def test_get_current_user_with_role_returns_role_and_tier(mocker):
    _mock_profile(mocker, role="admin", membership_tier=None)

    response = client.get(
        "/whoami-with-role", headers={"Authorization": "Bearer good-token"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["membership_tier"] is None
    assert body["id"] == "user-1"


def test_get_current_user_with_role_rejects_soft_deleted_user(mocker):
    _mock_profile(
        mocker,
        role="member",
        membership_tier="regular",
        deleted_at="2026-08-14T00:00:00Z",
    )

    response = client.get(
        "/whoami-with-role", headers={"Authorization": "Bearer good-token"}
    )

    assert response.status_code == 401


def test_get_current_user_with_role_rejects_missing_profile(mocker):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    fake_user = SimpleNamespace(id="user-1", email="a@b.com")
    mock_admin.return_value.auth.get_user.return_value = SimpleNamespace(user=fake_user)
    mock_admin.return_value.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        None
    )

    response = client.get(
        "/whoami-with-role", headers={"Authorization": "Bearer good-token"}
    )

    assert response.status_code == 401


def test_require_permission_allows_role_with_permission(mocker):
    _mock_profile(mocker, role="admin", membership_tier=None)

    response = client.get(
        "/members-only", headers={"Authorization": "Bearer good-token"}
    )

    assert response.status_code == 200


def test_require_permission_rejects_role_without_permission(mocker):
    _mock_profile(mocker, role="member", membership_tier="regular")

    response = client.get(
        "/members-only", headers={"Authorization": "Bearer good-token"}
    )

    assert response.status_code == 403
