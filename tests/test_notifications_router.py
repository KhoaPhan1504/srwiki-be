from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.routers import notifications

app = FastAPI()
app.include_router(notifications.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)

NOTIFICATION_ROW = {
    "id": "n1",
    "type": "phone_verified",
    "title": "Xác minh số điện thoại thành công",
    "message": "Số điện thoại +84912345678 đã được xác minh.",
    "metadata": {},
    "read_at": None,
    "created_at": "2026-08-11T00:00:00+00:00",
}


def test_list_notifications_returns_rows(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = SimpleNamespace(
        data=[NOTIFICATION_ROW]
    )
    mocker.patch("app.routers.notifications.user_client", return_value=fake_client)

    response = client.get("/notifications")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["type"] == "phone_verified"
    assert body[0]["readAt"] is None


def test_mark_notification_read_updates_row(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{**NOTIFICATION_ROW, "read_at": "2026-08-11T01:00:00+00:00"}]
    )
    mocker.patch("app.routers.notifications.user_client", return_value=fake_client)

    response = client.patch("/notifications/n1/read")

    assert response.status_code == 200
    assert response.json()["readAt"] is not None


def test_mark_notification_read_missing_returns_404(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[]
    )
    mocker.patch("app.routers.notifications.user_client", return_value=fake_client)

    response = client.patch("/notifications/missing/read")

    assert response.status_code == 404


def test_mark_all_notifications_read_returns_count(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.update.return_value.eq.return_value.is_.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": "n1"}, {"id": "n2"}]
    )
    mocker.patch("app.routers.notifications.user_client", return_value=fake_client)

    response = client.patch("/notifications/read-all")

    assert response.status_code == 200
    assert response.json() == {"markedCount": 2}
