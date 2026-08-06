from types import SimpleNamespace
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.dependencies import get_current_user

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
    assert response.json() == {"id": "user-1", "email": "a@b.com", "access_token": "good-token"}
