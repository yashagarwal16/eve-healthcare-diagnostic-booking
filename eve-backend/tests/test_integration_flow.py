"""
End-to-end tests against a real SQL Server instance (via docker-compose).

These are integration, not unit, tests -- they exercise the actual DB layer,
so they need `db` from docker-compose up and the schema applied
(`python scripts/init_db.py`). If the DB is unreachable, every test in this
module is skipped rather than erroring, so `python -m unittest discover`
still succeeds in environments without SQL Server running (e.g. a plain
laptop checkout, or this repo's CI lint step).

Run for real with:
    docker-compose up -d
    python scripts/init_db.py
    MSSQL_HOST=localhost python -m unittest tests.test_integration_flow -v
"""

import os
import unittest
import uuid

import pymssql

from app import create_app
from app.config import Config


def _db_reachable() -> bool:
    try:
        conn = pymssql.connect(
            server=Config.MSSQL_HOST,
            port=str(Config.MSSQL_PORT),
            user=Config.MSSQL_USER,
            password=Config.MSSQL_PASSWORD,
            database=Config.MSSQL_DB,
            login_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


DB_UP = _db_reachable()


@unittest.skipUnless(DB_UP, "SQL Server not reachable -- start it with docker-compose up")
class BookingPaymentFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

        unique = uuid.uuid4().hex[:8]
        self.email = f"test_{unique}@example.com"
        self.password = "testpass123"

        signup_resp = self.client.post(
            "/auth/signup",
            json={"name": "Test User", "email": self.email, "password": self.password},
        )
        self.assertEqual(signup_resp.status_code, 201)
        self.token = signup_resp.get_json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

        centre_resp = self.client.post(
            "/centres",
            json={"name": f"Centre {unique}", "location": "Test City"},
            headers=self.headers,
        )
        self.assertEqual(centre_resp.status_code, 201)
        self.centre_id = centre_resp.get_json()["id"]

        test_resp = self.client.post(
            f"/centres/{self.centre_id}/tests",
            json={"name": "Test Panel", "price": 500},
            headers=self.headers,
        )
        self.assertEqual(test_resp.status_code, 201)
        self.test_id = test_resp.get_json()["id"]

    def _create_booking(self):
        resp = self.client.post(
            "/bookings",
            json={"test_id": self.test_id, "appointment_time": "2026-11-01T10:00:00"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["id"]

    def test_signup_rejects_duplicate_email(self):
        resp = self.client.post(
            "/auth/signup",
            json={"name": "Dup", "email": self.email, "password": "whatever123"},
        )
        self.assertEqual(resp.status_code, 409)

    def test_login_with_wrong_password_fails(self):
        resp = self.client.post(
            "/auth/login", json={"email": self.email, "password": "wrong-password"}
        )
        self.assertEqual(resp.status_code, 401)

    def test_booking_lifecycle_to_confirmed_or_failed(self):
        booking_id = self._create_booking()

        get_resp = self.client.get(f"/bookings/{booking_id}", headers=self.headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.get_json()["status"], "PENDING")

        pay_resp = self.client.post(
            "/payments/", json={"booking_id": booking_id}, headers=self.headers
        )
        self.assertIn(pay_resp.status_code, (200, 201))
        self.assertIn(pay_resp.get_json()["booking_status"], ("CONFIRMED", "FAILED"))

        # Booking must no longer be payable a second time.
        second_pay = self.client.post(
            "/payments/", json={"booking_id": booking_id}, headers=self.headers
        )
        self.assertEqual(second_pay.status_code, 409)

    def test_other_user_cannot_view_booking(self):
        booking_id = self._create_booking()

        other_email = f"other_{uuid.uuid4().hex[:8]}@example.com"
        signup_resp = self.client.post(
            "/auth/signup",
            json={"name": "Other User", "email": other_email, "password": "otherpass123"},
        )
        other_token = signup_resp.get_json()["token"]

        resp = self.client.get(
            f"/bookings/{booking_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_get_nonexistent_booking_returns_404(self):
        resp = self.client.get("/bookings/99999999", headers=self.headers)
        self.assertEqual(resp.status_code, 404)

    def test_webhook_requires_valid_secret(self):
        booking_id = self._create_booking()
        resp = self.client.post(
            "/payments/webhook/",
            json={"event_id": "evt_1", "booking_id": booking_id, "status": "SUCCESS"},
            headers={"X-Webhook-Secret": "wrong-secret"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_webhook_is_idempotent_on_duplicate_event_id(self):
        booking_id = self._create_booking()
        event_id = f"evt_{uuid.uuid4().hex[:10]}"
        payload = {"event_id": event_id, "booking_id": booking_id, "status": "SUCCESS"}
        headers = {"X-Webhook-Secret": "sim-provider-secret"}

        first = self.client.post("/payments/webhook/", json=payload, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["booking_status"], "CONFIRMED")

        # Replay the exact same event three times.
        for _ in range(3):
            replay = self.client.post("/payments/webhook/", json=payload, headers=headers)
            self.assertEqual(replay.status_code, 200)
            self.assertEqual(replay.get_json()["booking_status"], "CONFIRMED")

        with pymssql.connect(
            server=Config.MSSQL_HOST,
            port=str(Config.MSSQL_PORT),
            user=Config.MSSQL_USER,
            password=Config.MSSQL_PASSWORD,
            database=Config.MSSQL_DB,
        ) as conn:
            cur = conn.cursor(as_dict=True)
            cur.execute(
                "SELECT COUNT(*) AS n FROM dbo.Payments WHERE booking_id = %s",
                (booking_id,),
            )
            payment_count = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM dbo.PaymentEvents WHERE booking_id = %s",
                (booking_id,),
            )
            event_count = cur.fetchone()["n"]

        # Despite 4 total webhook deliveries of the same event, exactly
        # one Payment and one PaymentEvent row must exist.
        self.assertEqual(payment_count, 1)
        self.assertEqual(event_count, 1)

    def test_webhook_does_not_override_already_confirmed_booking(self):
        booking_id = self._create_booking()
        headers = {"X-Webhook-Secret": "sim-provider-secret"}

        confirm = self.client.post(
            "/payments/webhook/",
            json={"event_id": f"evt_a_{uuid.uuid4().hex[:8]}", "booking_id": booking_id, "status": "SUCCESS"},
            headers=headers,
        )
        self.assertEqual(confirm.get_json()["booking_status"], "CONFIRMED")

        # A different event, arriving late, tries to mark it FAILED.
        # A CONFIRMED booking must never flip back to FAILED.
        late_fail = self.client.post(
            "/payments/webhook/",
            json={"event_id": f"evt_b_{uuid.uuid4().hex[:8]}", "booking_id": booking_id, "status": "FAILED"},
            headers=headers,
        )
        self.assertEqual(late_fail.status_code, 200)
        self.assertEqual(late_fail.get_json()["booking_status"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main()
