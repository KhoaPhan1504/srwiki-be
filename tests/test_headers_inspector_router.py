import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.http_inspection import (
    BlockedUrlError,
    ConnectionFailedError,
    HeaderInspectionError,
    HeaderInspectionResult,
    InvalidUrlError,
    RequestTimedOutError,
    TooManyRedirectsError,
)
from app.routers import headers_inspector

app = FastAPI()
app.include_router(headers_inspector.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def _result(**overrides):
    defaults = {
        "status_code": 200,
        "reason_phrase": "OK",
        "headers": (("content-type", "text/plain"),),
        "final_url": "https://example.com/",
        "redirect_count": 0,
        "duration_ms": 12.5,
        "http_version": "HTTP/1.1",
    }
    defaults.update(overrides)
    return HeaderInspectionResult(**defaults)


class TestInspectSuccess:
    def test_returns_headers_and_metadata_as_camel_case(self, mocker):
        mocker.patch(
            "app.routers.headers_inspector.inspect_headers",
            return_value=_result(
                headers=(
                    ("content-type", "application/json"),
                    ("x-a", "1"),
                    ("x-a", "2"),
                )
            ),
        )

        response = client.post(
            "/headers-inspector/inspect", json={"url": "https://example.com"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["statusCode"] == 200
        assert body["reasonPhrase"] == "OK"
        # Duplicate header names are preserved, not collapsed into a dict.
        assert body["headers"] == [
            {"name": "content-type", "value": "application/json"},
            {"name": "x-a", "value": "1"},
            {"name": "x-a", "value": "2"},
        ]
        assert body["finalUrl"] == "https://example.com/"
        assert body["redirectCount"] == 0
        assert body["durationMs"] == 12.5
        assert body["httpVersion"] == "HTTP/1.1"

    def test_non_2xx_target_status_is_still_a_200_api_response(self, mocker):
        mocker.patch(
            "app.routers.headers_inspector.inspect_headers",
            return_value=_result(status_code=404, reason_phrase="Not Found"),
        )

        response = client.post(
            "/headers-inspector/inspect", json={"url": "https://example.com/missing"}
        )

        assert response.status_code == 200
        assert response.json()["statusCode"] == 404
        assert response.json()["reasonPhrase"] == "Not Found"

    def test_calls_inspect_headers_with_the_payload_url(self, mocker):
        spy = mocker.patch(
            "app.routers.headers_inspector.inspect_headers", return_value=_result()
        )

        client.post(
            "/headers-inspector/inspect", json={"url": "https://example.com/foo"}
        )

        spy.assert_called_once_with("https://example.com/foo")


class TestInspectErrors:
    @pytest.mark.parametrize(
        "exc_cls,expected_status",
        [
            (InvalidUrlError, 400),
            (BlockedUrlError, 400),
            (ConnectionFailedError, 502),
            (RequestTimedOutError, 504),
            (TooManyRedirectsError, 502),
        ],
    )
    def test_maps_each_error_type_to_the_expected_http_status(
        self, mocker, exc_cls, expected_status
    ):
        mocker.patch(
            "app.routers.headers_inspector.inspect_headers",
            side_effect=exc_cls("boom"),
        )

        response = client.post(
            "/headers-inspector/inspect", json={"url": "https://example.com"}
        )

        assert response.status_code == expected_status
        assert response.json()["detail"] == {"code": exc_cls.code, "message": "boom"}

    def test_unmapped_error_subtype_returns_502_not_a_crash(self, mocker):
        # _ERROR_STATUS_CODES[type(exc)] is an exact-type dict lookup; any
        # HeaderInspectionError subtype that isn't one of the ones explicitly
        # listed above must still get a sane response instead of a KeyError
        # crashing the error handler itself (which FastAPI would turn into an
        # unhandled 500).
        class _UnmappedHeaderInspectionError(HeaderInspectionError):
            code = "SOME_UNEXPECTED_CODE"

        mocker.patch(
            "app.routers.headers_inspector.inspect_headers",
            side_effect=_UnmappedHeaderInspectionError("boom"),
        )

        response = client.post(
            "/headers-inspector/inspect", json={"url": "https://example.com"}
        )

        assert response.status_code == 502
        assert response.json()["detail"] == {
            "code": "SOME_UNEXPECTED_CODE",
            "message": "boom",
        }


class TestInspectRequestValidation:
    def test_rejects_missing_url(self):
        response = client.post("/headers-inspector/inspect", json={})
        assert response.status_code == 422

    def test_rejects_empty_url(self):
        response = client.post("/headers-inspector/inspect", json={"url": ""})
        assert response.status_code == 422

    def test_rejects_unknown_fields(self):
        response = client.post(
            "/headers-inspector/inspect",
            json={"url": "https://example.com", "method": "POST"},
        )
        assert response.status_code == 422

    def test_rejects_url_longer_than_max_length(self):
        oversized_url = "https://example.com/" + ("a" * 2048)
        response = client.post(
            "/headers-inspector/inspect", json={"url": oversized_url}
        )
        assert response.status_code == 422


class TestInspectAuth:
    def test_requires_bearer_token(self):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            response = client.post(
                "/headers-inspector/inspect", json={"url": "https://example.com"}
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides[get_current_user] = override_current_user
