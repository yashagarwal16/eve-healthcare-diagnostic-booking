import re
from datetime import datetime

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def require_fields(data: dict, fields: list[str]) -> None:
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")
    missing = [f for f in fields if f not in data or data[f] in (None, "")]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}")


def validate_email(email: str) -> None:
    if not isinstance(email, str) or not EMAIL_RE.match(email):
        raise ValidationError("Invalid email format")


def validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters")


def parse_datetime(value: str) -> datetime:
    """Accepts ISO 8601, e.g. '2026-10-05T14:30:00'."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(
            "appointment_time must be ISO 8601, e.g. 2026-10-05T14:30:00"
        )


def positive_int(value, field_name: str) -> int:
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be an integer")
    if ivalue <= 0:
        raise ValidationError(f"{field_name} must be a positive integer")
    return ivalue
