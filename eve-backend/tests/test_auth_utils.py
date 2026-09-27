import time
import unittest

import jwt

from app.auth import hash_password, verify_password, issue_token, decode_token
from app.config import Config


class PasswordHashingTests(unittest.TestCase):
    def test_correct_password_verifies(self):
        h = hash_password("correct-horse-battery-staple")
        self.assertTrue(verify_password("correct-horse-battery-staple", h))

    def test_wrong_password_fails(self):
        h = hash_password("correct-horse-battery-staple")
        self.assertFalse(verify_password("wrong-password", h))

    def test_hash_is_not_plaintext(self):
        h = hash_password("mysecret")
        self.assertNotEqual(h, "mysecret")


class JwtTests(unittest.TestCase):
    def test_issued_token_decodes_to_same_user(self):
        token = issue_token(user_id=42, email="user@example.com")
        payload = decode_token(token)
        self.assertEqual(payload["sub"], 42)
        self.assertEqual(payload["email"], "user@example.com")

    def test_tampered_token_is_rejected(self):
        token = issue_token(user_id=1, email="a@b.com")
        tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
        with self.assertRaises(jwt.PyJWTError):
            decode_token(tampered)

    def test_expired_token_is_rejected(self):
        original_expiry = Config.JWT_EXPIRY_MINUTES
        try:
            # Issue a token that expires almost immediately, then wait it out.
            Config.JWT_EXPIRY_MINUTES = 0
            token = issue_token(user_id=1, email="a@b.com")
            time.sleep(1.5)
            with self.assertRaises(jwt.ExpiredSignatureError):
                decode_token(token)
        finally:
            Config.JWT_EXPIRY_MINUTES = original_expiry


if __name__ == "__main__":
    unittest.main()
