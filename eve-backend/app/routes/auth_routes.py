import logging

import pymssql
from flask import Blueprint, request, jsonify

from app.auth import hash_password, verify_password, issue_token
from app.db import get_cursor
from app.validation import require_fields, validate_email, validate_password, ValidationError

logger = logging.getLogger("eve.auth")
auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/signup")
def signup():
    data = request.get_json(silent=True) or {}
    try:
        require_fields(data, ["name", "email", "password"])
        validate_email(data["email"])
        validate_password(data["password"])
    except ValidationError as e:
        return jsonify(error=e.message), 400

    pw_hash = hash_password(data["password"])

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO dbo.Users (name, email, password_hash) "
                "OUTPUT INSERTED.id VALUES (%s, %s, %s)",
                (data["name"], data["email"], pw_hash),
            )
            new_id = cur.fetchone()["id"]
    except pymssql.IntegrityError:
        # Unique constraint on email fired -> account already exists.
        return jsonify(error="An account with this email already exists"), 409

    token = issue_token(new_id, data["email"])
    logger.info("user signed up", extra={"user_id": new_id})
    return jsonify(id=new_id, name=data["name"], email=data["email"], token=token), 201


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    try:
        require_fields(data, ["email", "password"])
    except ValidationError as e:
        return jsonify(error=e.message), 400

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, name, email, password_hash FROM dbo.Users WHERE email = %s",
            (data["email"],),
        )
        user = cur.fetchone()

    # Deliberately identical error for "no such user" and "wrong password"
    # so the endpoint doesn't leak which emails are registered.
    if not user or not verify_password(data["password"], user["password_hash"]):
        return jsonify(error="Invalid email or password"), 401

    token = issue_token(user["id"], user["email"])
    logger.info("user logged in", extra={"user_id": user["id"]})
    return jsonify(id=user["id"], name=user["name"], email=user["email"], token=token), 200
