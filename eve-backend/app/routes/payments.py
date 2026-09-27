import logging
import random
import uuid
import json

import pymssql
from flask import Blueprint, request, jsonify, g

from app.auth import login_required
from app.config import Config
from app.db import get_cursor
from app.validation import require_fields, ValidationError

logger = logging.getLogger("eve.payments")
payments_bp = Blueprint("payments", __name__)

WEBHOOK_SHARED_SECRET = "sim-provider-secret"  # see README: mock, not for production


def _simulate_outcome() -> str:
    return "SUCCESS" if random.random() < Config.PAYMENT_SUCCESS_RATE else "FAILED"


@payments_bp.post("/")
@login_required
def create_payment():
    """
    Simulates a synchronous payment attempt against a booking the caller
    owns. In a real integration this would call out to a gateway and
    return a redirect/intent; here it resolves immediately to
    SUCCESS/FAILED and updates the booking in the same request.
    """
    data = request.get_json(silent=True) or {}
    try:
        require_fields(data, ["booking_id"])
    except ValidationError as e:
        return jsonify(error=e.message), 400

    try:
        booking_id = int(data["booking_id"])
    except (TypeError, ValueError):
        return jsonify(error="booking_id must be an integer"), 400

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, user_id, amount, status FROM dbo.Bookings WHERE id = %s",
            (booking_id,),
        )
        booking = cur.fetchone()

    if not booking:
        return jsonify(error="Booking not found"), 404
    if booking["user_id"] != g.user_id:
        return jsonify(error="You are not authorized to pay for this booking"), 403
    if booking["status"] != "PENDING":
        return (
            jsonify(error=f"Booking is not payable in its current status: {booking['status']}"),
            409,
        )

    outcome = _simulate_outcome()
    new_booking_status = "CONFIRMED" if outcome == "SUCCESS" else "FAILED"
    provider_ref = f"sim_{uuid.uuid4().hex[:12]}"

    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO dbo.Payments (booking_id, amount, status, provider_reference) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s, %s)",
            (booking_id, booking["amount"], outcome, provider_ref),
        )
        payment_id = cur.fetchone()["id"]
        cur.execute(
            "UPDATE dbo.Bookings SET status = %s, updated_at = SYSUTCDATETIME() WHERE id = %s",
            (new_booking_status, booking_id),
        )

    logger.info(
        "payment simulated",
        extra={"booking_id": booking_id, "user_id": g.user_id},
    )
    return (
        jsonify(
            payment_id=payment_id,
            booking_id=booking_id,
            status=outcome,
            provider_reference=provider_ref,
            booking_status=new_booking_status,
        ),
        201 if outcome == "SUCCESS" else 200,
    )


@payments_bp.post("/webhook/")
def payment_webhook():
    """
    Simulates an async callback from a payment provider.

    Idempotency: every inbound event carries a provider-issued `event_id`.
    We try to INSERT it into PaymentEvents, which has a UNIQUE constraint
    on event_id. If that insert fails with an integrity error, this exact
    event was already processed -- we return 200 with the original
    recorded outcome and do NOT touch the booking again. This holds even
    under concurrent duplicate deliveries, since the uniqueness is
    enforced by the database, not by a check-then-act read in Python.
    """
    secret = request.headers.get("X-Webhook-Secret", "")
    if secret != WEBHOOK_SHARED_SECRET:
        return jsonify(error="Invalid webhook signature"), 401

    data = request.get_json(silent=True) or {}
    try:
        require_fields(data, ["event_id", "booking_id", "status"])
    except ValidationError as e:
        return jsonify(error=e.message), 400

    if data["status"] not in ("SUCCESS", "FAILED"):
        return jsonify(error="status must be SUCCESS or FAILED"), 400

    try:
        booking_id = int(data["booking_id"])
    except (TypeError, ValueError):
        return jsonify(error="booking_id must be an integer"), 400

    event_id = str(data["event_id"])

    with get_cursor() as cur:
        cur.execute("SELECT id FROM dbo.Bookings WHERE id = %s", (booking_id,))
        if not cur.fetchone():
            return jsonify(error="Booking not found"), 404

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.PaymentEvents (event_id, booking_id, status, raw_payload) "
                "VALUES (%s, %s, %s, %s)",
                (event_id, booking_id, data["status"], json.dumps(data)),
            )

            cur.execute(
                "SELECT status FROM dbo.Bookings WHERE id = %s", (booking_id,)
            )
            current_status = cur.fetchone()["status"]

            # Only transition a booking that is still PENDING. A booking
            # that was already CONFIRMED/FAILED/CANCELLED (e.g. via the
            # synchronous /payments/ endpoint, or an operator action)
            # is never overwritten by a late/duplicate webhook.
            if current_status == "PENDING":
                new_status = "CONFIRMED" if data["status"] == "SUCCESS" else "FAILED"
                cur.execute(
                    "SELECT amount FROM dbo.Bookings WHERE id = %s", (booking_id,)
                )
                amount = cur.fetchone()["amount"]
                cur.execute(
                    "INSERT INTO dbo.Payments (booking_id, amount, status, provider_reference) "
                    "VALUES (%s, %s, %s, %s)",
                    (booking_id, amount, data["status"], event_id),
                )
                cur.execute(
                    "UPDATE dbo.Bookings SET status = %s, updated_at = SYSUTCDATETIME() "
                    "WHERE id = %s",
                    (new_status, booking_id),
                )
                current_status = new_status
            else:
                logger.info(
                    "webhook received for non-pending booking, booking left unchanged",
                    extra={"booking_id": booking_id, "event_id": event_id},
                )

        logger.info(
            "webhook processed", extra={"booking_id": booking_id, "event_id": event_id}
        )
        return jsonify(event_id=event_id, booking_id=booking_id, booking_status=current_status), 200

    except pymssql.IntegrityError:
        # Duplicate event_id -- already processed. Look up what happened
        # the first time and return that, rather than reprocessing.
        with get_cursor() as cur:
            cur.execute(
                "SELECT status FROM dbo.Bookings WHERE id = %s", (booking_id,)
            )
            current_status = cur.fetchone()["status"]
        logger.info(
            "duplicate webhook event ignored",
            extra={"booking_id": booking_id, "event_id": event_id},
        )
        return (
            jsonify(
                event_id=event_id,
                booking_id=booking_id,
                booking_status=current_status,
                note="duplicate event, already processed",
            ),
            200,
        )
