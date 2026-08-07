import pytest
from pydantic import ValidationError
from app.schemas import RegisterRequest, ProfileUpdateRequest, ProfileOut


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


def test_register_request_accepts_camel_case_full_name():
    req = RegisterRequest(email="a@b.com", password="password123", fullName="A B")
    assert req.full_name == "A B"


def test_register_request_serializes_full_name_as_camel_case():
    req = RegisterRequest(email="a@b.com", password="password123", full_name="A B")
    assert req.model_dump(by_alias=True)["fullName"] == "A B"


def test_profile_update_request_accepts_camel_case_date_of_birth():
    req = ProfileUpdateRequest(dateOfBirth="2000-01-01")
    assert req.date_of_birth is not None


def test_profile_out_serializes_with_camel_case_aliases():
    profile = ProfileOut(
        id="u1",
        email="a@b.com",
        full_name="A B",
        phone=None,
        phone_verified=True,
        address=None,
        date_of_birth=None,
        avatar_url=None,
        bio=None,
        created_at="2026-08-05T00:00:00Z",
        updated_at="2026-08-05T00:00:00Z",
    )
    dumped = profile.model_dump(by_alias=True)
    assert dumped["fullName"] == "A B"
    assert dumped["phoneVerified"] is True
    assert dumped["dateOfBirth"] is None
    assert dumped["createdAt"] is not None
    assert dumped["avatarUrl"] is None
    assert dumped["bio"] is None
