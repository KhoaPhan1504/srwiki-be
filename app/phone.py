import phonenumbers


class InvalidPhoneNumberError(ValueError):
    pass


def validate_phone_e164(phone: str) -> str:
    try:
        parsed = phonenumbers.parse(phone, None)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumberError(str(exc)) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumberError(f"'{phone}' is not a valid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
