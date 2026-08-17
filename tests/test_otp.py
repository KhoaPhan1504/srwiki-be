import re

from app.otp import generate_code


def test_generate_code_is_six_digits():
    codes = [generate_code() for _ in range(200)]
    assert all(re.fullmatch(r"\d{6}", code) for code in codes)
    assert len(set(codes)) > 1
