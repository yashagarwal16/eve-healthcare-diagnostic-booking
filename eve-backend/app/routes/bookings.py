import logging

from flask import Blueprint, request, jsonify, g

from app.auth import login_required
from app.db import get_cursor
from app.validation import require_fields, parse_datetime, ValidationError

logger = logging.getLogger("eve.bookings")
bookings_bp = Blueprint("bookings", __name__)


@bookings_bp.post("")
@login_required
def create_booking():
    """
    Books a diagnostic test. The test's current price is snapshotted onto
    the booking as `amount` -- if the centre changes the test price later,
    already-made bookings are unaffected.
    """
    data = request.get_json(silent=True) or {}
    try:
        require_fields(data, ["test_id", "appointment_time"])
        appointment_dt = parse_datetime(data["appointment_time"])
    except ValidationError as e:
        return jsonify(error=e.message), 400

    try:
        test_id = int(data["test_id"])
    except (TypeError, ValueError):
        return jsonify(error="test_id must be an integer"), 400

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, centre_id, price FROM dbo.Tests WHERE id = %s", (test_id,)
        )
        test = cur.fetchone()

    if not test:
        return jsonify(error="Diagnostic test not found"), 404

    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO dbo.Bookings "
            "(user_id, test_id, centre_id, appointment_time, amount, status) "
            "OUTPUT INSERTED.id "
            "VALUES (%s, %s, %s, %s, %s, 'PENDING')",
            (g.user_id, test_id, test["centre_id"], appointment_dt, test["price"]),
        )
        booking_id = cur.fetchone()["id"]

    logger.info("booking created", extra={"booking_id": booking_id, "user_id": g.user_id})
    return (
        jsonify(
            id=booking_id,
            test_id=test_id,
            centre_id=test["centre_id"],
            appointment_time=data["appointment_time"],
            amount=float(test["price"]),
            status="PENDING",
        ),
        201,
    )


@bookings_bp.get("/<int:booking_id>")
@login_required
def get_booking(booking_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, user_id, test_id, centre_id, appointment_time, amount, status "
            "FROM dbo.Bookings WHERE id = %s",
            (booking_id,),
        )
        booking = cur.fetchone()

    if not booking:
        return jsonify(error="Booking not found"), 404

    if booking["user_id"] != g.user_id:
        return jsonify(error="You are not authorized to view this booking"), 403

    booking["amount"] = float(booking["amount"])
    booking["appointment_time"] = booking["appointment_time"].isoformat()
    return jsonify(booking), 200


@bookings_bp.get("")
@login_required
def list_my_bookings():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    except ValueError:
        return jsonify(error="page and page_size must be integers"), 400

    offset = (page - 1) * page_size
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, test_id, centre_id, appointment_time, amount, status "
            "FROM dbo.Bookings WHERE user_id = %s "
            "ORDER BY id DESC OFFSET %s ROWS FETCH NEXT %s ROWS ONLY",
            (g.user_id, offset, page_size),
        )
        rows = cur.fetchall()

    for r in rows:
        r["amount"] = float(r["amount"])
        r["appointment_time"] = r["appointment_time"].isoformat()

    return jsonify(page=page, page_size=page_size, bookings=rows), 200


@bookings_bp.post("/<int:booking_id>/cancel")
@login_required
def cancel_booking(booking_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, user_id, status FROM dbo.Bookings WHERE id = %s", (booking_id,)
        )
        booking = cur.fetchone()

    if not booking:
        return jsonify(error="Booking not found"), 404
    if booking["user_id"] != g.user_id:
        return jsonify(error="You are not authorized to modify this booking"), 403
    if booking["status"] in ("CANCELLED", "CONFIRMED"):
        return (
            jsonify(error=f"Cannot cancel a booking that is already {booking['status']}"),
            409,
        )

    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE dbo.Bookings SET status = 'CANCELLED', updated_at = SYSUTCDATETIME() "
            "WHERE id = %s",
            (booking_id,),
        )

    logger.info("booking cancelled", extra={"booking_id": booking_id, "user_id": g.user_id})
    return jsonify(id=booking_id, status="CANCELLED"), 200
