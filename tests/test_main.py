from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_all_expected_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert {
        "/health",
        "/auth/register",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/profile",
        "/profile/phone/send-otp",
        "/profile/phone/verify-otp",
    } <= paths


def test_cors_headers_present_for_allowed_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )
