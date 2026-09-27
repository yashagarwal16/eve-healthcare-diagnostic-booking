import unittest

from app.validation import (
    require_fields,
    validate_email,
    validate_password,
    parse_datetime,
    positive_int,
    ValidationError,
)


class RequireFieldsTests(unittest.TestCase):
    def test_passes_when_all_fields_present(self):
        require_fields({"a": 1, "b": 2}, ["a", "b"])  # should not raise

    def test_raises_when_field_missing(self):
        with self.assertRaises(ValidationError):
            require_fields({"a": 1}, ["a", "b"])

    def test_raises_when_field_is_empty_string(self):
        with self.assertRaises(ValidationError):
            require_fields({"a": ""}, ["a"])

    def test_raises_when_body_not_a_dict(self):
        with self.assertRaises(ValidationError):
            require_fields(["not", "a", "dict"], ["a"])


class EmailValidationTests(unittest.TestCase):
    def test_accepts_valid_email(self):
        validate_email("user@example.com")  # should not raise

    def test_rejects_missing_at_sign(self):
        with self.assertRaises(ValidationError):
            validate_email("userexample.com")

    def test_rejects_missing_domain_dot(self):
        with self.assertRaises(ValidationError):
            validate_email("user@example")

    def test_rejects_non_string(self):
        with self.assertRaises(ValidationError):
            validate_email(12345)


class PasswordValidationTests(unittest.TestCase):
    def test_accepts_password_of_min_length(self):
        validate_password("12345678")  # should not raise

    def test_rejects_short_password(self):
        with self.assertRaises(ValidationError):
            validate_password("short")


class DatetimeParsingTests(unittest.TestCase):
    def test_parses_valid_iso_datetime(self):
        dt = parse_datetime("2026-10-05T14:30:00")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.hour, 14)

    def test_rejects_invalid_format(self):
        with self.assertRaises(ValidationError):
            parse_datetime("05/10/2026 2:30 PM")

    def test_rejects_none(self):
        with self.assertRaises(ValidationError):
            parse_datetime(None)


class PositiveIntTests(unittest.TestCase):
    def test_accepts_positive_integer(self):
        self.assertEqual(positive_int("5", "test_id"), 5)

    def test_rejects_zero(self):
        with self.assertRaises(ValidationError):
            positive_int(0, "test_id")

    def test_rejects_negative(self):
        with self.assertRaises(ValidationError):
            positive_int(-3, "test_id")

    def test_rejects_non_numeric_string(self):
        with self.assertRaises(ValidationError):
            positive_int("abc", "test_id")


if __name__ == "__main__":
    unittest.main()
