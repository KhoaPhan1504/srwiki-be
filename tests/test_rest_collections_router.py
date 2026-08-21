from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.routers import rest_collections

app = FastAPI()
app.include_router(rest_collections.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)

COLLECTION_ID = "11111111-1111-1111-1111-111111111111"
MISSING_COLLECTION_ID = "22222222-2222-2222-2222-222222222222"
REQUEST_ID = "33333333-3333-3333-3333-333333333333"
MISSING_REQUEST_ID = "44444444-4444-4444-4444-444444444444"

COLLECTION_ROW = {
    "id": COLLECTION_ID,
    "name": "My Collection",
    "created_at": "2026-08-21T00:00:00+00:00",
}

SAVED_REQUEST_ROW = {
    "id": REQUEST_ID,
    "collection_id": COLLECTION_ID,
    "user_id": "user-1",
    "name": "Get profile",
    "method": "GET",
    "url": "https://api.example.com/profile",
    "query_params": [],
    "headers": [],
    "body": "",
    "body_type": "raw",
    "body_fields": [],
    "auth": {"type": "none"},
    "created_at": "2026-08-21T00:00:00+00:00",
    "updated_at": "2026-08-21T00:00:00+00:00",
}


def _fake_client_for_list(mocker, collection_rows, request_rows):
    fake_client = mocker.MagicMock()
    fake_collections_query = mocker.MagicMock()
    fake_collections_query.select.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(
        data=collection_rows
    )
    fake_requests_query = mocker.MagicMock()
    fake_requests_query.select.return_value.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(
        data=request_rows
    )
    fake_client.table.side_effect = lambda name: (
        fake_collections_query if name == "rest_collections" else fake_requests_query
    )
    return fake_client, fake_collections_query, fake_requests_query


def test_list_collections_empty(mocker):
    fake_client, _, _ = _fake_client_for_list(mocker, [], [])
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.get("/rest-client/collections")

    assert response.status_code == 200
    assert response.json() == []


def test_list_collections_groups_requests_by_collection_id(mocker):
    fake_client, fake_collections_query, fake_requests_query = _fake_client_for_list(
        mocker, [COLLECTION_ROW], [SAVED_REQUEST_ROW]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.get("/rest-client/collections")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == COLLECTION_ID
    assert len(body[0]["requests"]) == 1
    assert body[0]["requests"][0]["id"] == REQUEST_ID
    # Verify both queries were scoped to the current user
    fake_collections_query.select.return_value.eq.assert_called_with(
        "user_id", "user-1"
    )
    fake_requests_query.select.return_value.eq.assert_called_with("user_id", "user-1")


def test_create_collection_inserts_scoped_to_user(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.insert.return_value.execute.return_value = (
        SimpleNamespace(data=[COLLECTION_ROW])
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.post("/rest-client/collections", json={"name": "My Collection"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == COLLECTION_ID
    assert body["requests"] == []
    inserted = fake_client.table.return_value.insert.call_args[0][0]
    assert inserted["user_id"] == "user-1"
    assert inserted["name"] == "My Collection"


def test_create_collection_rejects_blank_name():
    response = client.post("/rest-client/collections", json={"name": ""})
    assert response.status_code == 422


def test_rename_collection_updates_scoped_row(mocker):
    fake_client = mocker.MagicMock()
    renamed = {**COLLECTION_ROW, "name": "Renamed"}
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[renamed]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.patch(
        f"/rest-client/collections/{COLLECTION_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    fake_client.table.return_value.update.return_value.eq.assert_called_with(
        "id", COLLECTION_ID
    )
    fake_client.table.return_value.update.return_value.eq.return_value.eq.assert_called_with(
        "user_id", "user-1"
    )


def test_rename_collection_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.patch(
        f"/rest-client/collections/{MISSING_COLLECTION_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 404


def test_delete_collection_removes_scoped_row(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[COLLECTION_ROW]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.delete(f"/rest-client/collections/{COLLECTION_ID}")

    assert response.status_code == 204
    fake_client.table.return_value.delete.return_value.eq.assert_called_with(
        "id", COLLECTION_ID
    )
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.assert_called_with(
        "user_id", "user-1"
    )


def test_delete_collection_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.delete(f"/rest-client/collections/{MISSING_COLLECTION_ID}")

    assert response.status_code == 404


def _saved_request_payload():
    return {
        "name": "Get profile",
        "method": "GET",
        "url": "https://api.example.com/profile",
        "queryParams": [],
        "headers": [],
        "body": "",
        "bodyType": "raw",
        "bodyFields": [],
        "auth": {"type": "none"},
    }


def test_create_saved_request_inserts_scoped_to_collection(mocker):
    fake_client = mocker.MagicMock()
    fake_collection_lookup = mocker.MagicMock()
    fake_collection_lookup.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={"id": COLLECTION_ID}
    )
    fake_insert = mocker.MagicMock()
    fake_insert.insert.return_value.execute.return_value = SimpleNamespace(
        data=[SAVED_REQUEST_ROW]
    )
    fake_client.table.side_effect = lambda name: (
        fake_collection_lookup if name == "rest_collections" else fake_insert
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.post(
        f"/rest-client/collections/{COLLECTION_ID}/requests",
        json=_saved_request_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == REQUEST_ID
    assert body["method"] == "GET"
    inserted = fake_insert.insert.call_args[0][0]
    assert inserted["collection_id"] == COLLECTION_ID
    assert inserted["user_id"] == "user-1"


def test_create_saved_request_collection_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_collection_lookup = mocker.MagicMock()
    fake_collection_lookup.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=None
    )
    fake_client.table.return_value = fake_collection_lookup
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.post(
        f"/rest-client/collections/{MISSING_COLLECTION_ID}/requests",
        json=_saved_request_payload(),
    )

    assert response.status_code == 404


def test_create_saved_request_rejects_invalid_method():
    response = client.post(
        f"/rest-client/collections/{COLLECTION_ID}/requests",
        json={**_saved_request_payload(), "method": "TRACE"},
    )
    assert response.status_code == 422


def test_update_saved_request_sends_only_provided_fields(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{**SAVED_REQUEST_ROW, "name": "Renamed"}]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.patch(
        f"/rest-client/requests/{REQUEST_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    update_call = fake_client.table.return_value.update.call_args[0][0]
    assert update_call == {"name": "Renamed"}


def test_update_saved_request_overwrites_full_state(mocker):
    fake_client = mocker.MagicMock()
    updated_row = {**SAVED_REQUEST_ROW, "url": "https://api.example.com/v2/profile"}
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[updated_row]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.patch(
        f"/rest-client/requests/{REQUEST_ID}",
        json={"url": "https://api.example.com/v2/profile", "method": "POST"},
    )

    assert response.status_code == 200
    update_call = fake_client.table.return_value.update.call_args[0][0]
    assert update_call == {
        "url": "https://api.example.com/v2/profile",
        "method": "POST",
    }


def test_update_saved_request_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.patch(
        f"/rest-client/requests/{MISSING_REQUEST_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 404


def test_delete_saved_request_removes_scoped_row(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[SAVED_REQUEST_ROW]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.delete(f"/rest-client/requests/{REQUEST_ID}")

    assert response.status_code == 204
    fake_client.table.return_value.delete.return_value.eq.assert_called_with(
        "id", REQUEST_ID
    )
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.assert_called_with(
        "user_id", "user-1"
    )


def test_delete_saved_request_not_owned_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.rest_collections.user_client", return_value=fake_client)

    response = client.delete(f"/rest-client/requests/{MISSING_REQUEST_ID}")

    assert response.status_code == 404
