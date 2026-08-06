import pytest
from pydantic import ValidationError
from app.schemas import RegisterRequest, ProfileUpdateRequest


def test_register_request_accepts_valid_data():
    req = RegisterRequest(email="a@b.com", password="password123", full_name="A B")
    assert req.email == "a@b.com"


def test_register_request_rejects_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.com", password="short", full_name="A B")


def test_register_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="password123", full_name="A B")


def test_profile_update_request_rejects_phone_field():
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(phone="+84912345678")
