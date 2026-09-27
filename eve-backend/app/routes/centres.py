import logging

from flask import Blueprint, request, jsonify

from app.auth import login_required
from app.db import get_cursor
from app.validation import require_fields, ValidationError

logger = logging.getLogger("eve.centres")
centres_bp = Blueprint("centres", __name__)


@centres_bp.get("")
def list_centres():
    """
    GET /centres?page=1&page_size=20
    Returns centres with their available tests nested, paginated at the
    centre level.
    """
    try:
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    except ValueError:
        return jsonify(error="page and page_size must be integers"), 400

    offset = (page - 1) * page_size

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, location FROM dbo.Centres "
            "ORDER BY id OFFSET %s ROWS FETCH NEXT %s ROWS ONLY",
            (offset, page_size),
        )
        centres = cur.fetchall()

        if not centres:
            return jsonify(page=page, page_size=page_size, centres=[]), 200

        centre_ids = [c["id"] for c in centres]
        placeholders = ",".join(["%s"] * len(centre_ids))
        cur.execute(
            f"SELECT id, centre_id, name, price FROM dbo.Tests "
            f"WHERE centre_id IN ({placeholders})",
            tuple(centre_ids),
        )
        tests_by_centre = {}
        for t in cur.fetchall():
            tests_by_centre.setdefault(t["centre_id"], []).append(
                {"id": t["id"], "name": t["name"], "price": float(t["price"])}
            )

    for c in centres:
        c["tests"] = tests_by_centre.get(c["id"], [])

    return jsonify(page=page, page_size=page_size, centres=centres), 200


@centres_bp.post("")
@login_required
def create_centre():
    """
    Any authenticated user can register a centre for this assignment's
    scope -- a real system would gate this behind an admin/staff role,
    called out as a known simplification in the README.
    """
    data = request.get_json(silent=True) or {}
    try:
        require_fields(data, ["name", "location"])
    except ValidationError as e:
        return jsonify(error=e.message), 400

    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO dbo.Centres (name, location) OUTPUT INSERTED.id VALUES (%s, %s)",
            (data["name"], data["location"]),
        )
        new_id = cur.fetchone()["id"]

    logger.info("centre created", extra={"booking_id": None})
    return jsonify(id=new_id, name=data["name"], location=data["location"]), 201


@centres_bp.post("/<int:centre_id>/tests")
@login_required
def add_test(centre_id):
    data = request.get_json(silent=True) or {}
    try:
        require_fields(data, ["name", "price"])
    except ValidationError as e:
        return jsonify(error=e.message), 400

    try:
        price = float(data["price"])
        if price < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify(error="price must be a non-negative number"), 400

    with get_cursor() as cur:
        cur.execute("SELECT id FROM dbo.Centres WHERE id = %s", (centre_id,))
        if not cur.fetchone():
            return jsonify(error="Centre not found"), 404

    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO dbo.Tests (centre_id, name, price) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s)",
            (centre_id, data["name"], price),
        )
        new_id = cur.fetchone()["id"]

    return jsonify(id=new_id, centre_id=centre_id, name=data["name"], price=price), 201
