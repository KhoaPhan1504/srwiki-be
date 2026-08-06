import pytest
from app.phone import validate_phone_e164, InvalidPhoneNumberError


def test_valid_vietnam_number_returns_e164():
    assert validate_phone_e164("+84912345678") == "+84912345678"


def test_missing_plus_prefix_is_rejected():
    with pytest.raises(InvalidPhoneNumberError):
        validate_phone_e164("0912345678")


def test_garbage_input_is_rejected():
    with pytest.raises(InvalidPhoneNumberError):
        validate_phone_e164("+1234")
