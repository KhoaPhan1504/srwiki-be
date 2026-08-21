from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.routers import rest_environments

app = FastAPI()
app.include_router(rest_environments.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)

ENVIRONMENT_ID = "11111111-1111-1111-1111-111111111111"
MISSING_ENVIRONMENT_ID = "22222222-2222-2222-2222-222222222222"

ENVIRONMENT_ROW = {
    "id": ENVIRONMENT_ID,
    "name": "Dev",
    "variables": [
        {"id": "v1", "key": "base_url", "value": "https://dev.api", "enabled": True}
    ],
    "created_at": "2026-08-21T00:00:00+00:00",
    "updated_at": "2026-08-21T00:00:00+00:00",
}


def test_list_environments_empty(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.get("/rest-client/environments")

    assert response.status_code == 200
    assert response.json() == []


def test_list_environments_returns_rows_scoped_to_user(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(
        data=[ENVIRONMENT_ROW]
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.get("/rest-client/environments")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == ENVIRONMENT_ID
    assert body[0]["variables"][0]["key"] == "base_url"
    fake_client.table.return_value.select.return_value.eq.assert_called_with(
        "user_id", "user-1"
    )


def test_create_environment_inserts_scoped_to_user(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.insert.return_value.execute.return_value = (
        SimpleNamespace(data=[ENVIRONMENT_ROW])
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.post("/rest-client/environments", json={"name": "Dev"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == ENVIRONMENT_ID
    inserted = fake_client.table.return_value.insert.call_args[0][0]
    assert inserted["user_id"] == "user-1"
    assert inserted["name"] == "Dev"
    assert inserted["variables"] == []


def test_create_environment_rejects_blank_name():
    response = client.post("/rest-client/environments", json={"name": ""})
    assert response.status_code == 422


def test_update_environment_sends_only_provided_fields(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{**ENVIRONMENT_ROW, "name": "Renamed"}]
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.patch(
        f"/rest-client/environments/{ENVIRONMENT_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    update_call = fake_client.table.return_value.update.call_args[0][0]
    assert update_call == {"name": "Renamed"}


def test_update_environment_overwrites_variables(mocker):
    fake_client = mocker.MagicMock()
    new_vars = [{"id": "v2", "key": "token", "value": "xyz", "enabled": True}]
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{**ENVIRONMENT_ROW, "variables": new_vars}]
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.patch(
        f"/rest-client/environments/{ENVIRONMENT_ID}", json={"variables": new_vars}
    )

    assert response.status_code == 200
    assert response.json()["variables"] == new_vars
    update_call = fake_client.table.return_value.update.call_args[0][0]
    assert update_call == {"variables": new_vars}


def test_update_environment_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.patch(
        f"/rest-client/environments/{MISSING_ENVIRONMENT_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 404


def test_delete_environment_removes_scoped_row(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[ENVIRONMENT_ROW]
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.delete(f"/rest-client/environments/{ENVIRONMENT_ID}")

    assert response.status_code == 204
    fake_client.table.return_value.delete.return_value.eq.assert_called_with(
        "id", ENVIRONMENT_ID
    )
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.assert_called_with(
        "user_id", "user-1"
    )


def test_delete_environment_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.delete(f"/rest-client/environments/{MISSING_ENVIRONMENT_ID}")

    assert response.status_code == 404


def test_get_global_variables_returns_empty_when_no_row(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        None
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.get("/rest-client/global-variables")

    assert response.status_code == 200
    assert response.json() == {"variables": []}


def test_get_global_variables_returns_stored_values(mocker):
    fake_client = mocker.MagicMock()
    stored = [{"id": "v1", "key": "token", "value": "abc", "enabled": True}]
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={"variables": stored}
    )
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.get("/rest-client/global-variables")

    assert response.status_code == 200
    assert response.json()["variables"] == stored


def test_update_global_variables_upserts_scoped_to_user(mocker):
    fake_client = mocker.MagicMock()
    new_vars = [{"id": "v1", "key": "token", "value": "abc", "enabled": True}]
    mocker.patch("app.routers.rest_environments.user_client", return_value=fake_client)

    response = client.patch(
        "/rest-client/global-variables", json={"variables": new_vars}
    )

    assert response.status_code == 200
    assert response.json()["variables"] == new_vars
    upsert_call = fake_client.table.return_value.upsert.call_args
    assert upsert_call[0][0]["user_id"] == "user-1"
    assert upsert_call[0][0]["variables"] == new_vars
    assert upsert_call[1]["on_conflict"] == "user_id"


def test_update_global_variables_rejects_missing_field():
    response = client.patch("/rest-client/global-variables", json={})
    assert response.status_code == 422
