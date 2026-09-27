import datetime
from functools import wraps

import jwt
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from app.config import Config


def hash_password(plain_password: str) -> str:
    return generate_password_hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, plain_password)


def issue_token(user_id: int, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=Config.JWT_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError subclasses on invalid/expired tokens."""
    return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])


def login_required(fn):
    """
    Reads 'Authorization: Bearer <token>', validates it, and stashes the
    authenticated user id on flask.g.user_id for the view to use.

    Kept as a plain hand-written decorator (rather than Flask-JWT-Extended)
    so the whole auth flow is a few readable lines instead of a library
    black box -- deliberate, given this needs to be explained live.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify(error="Missing or malformed Authorization header"), 401

        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify(error="Token has expired"), 401
        except jwt.PyJWTError:
            return jsonify(error="Invalid token"), 401

        g.user_id = payload["sub"]
        g.user_email = payload.get("email")
        return fn(*args, **kwargs)

    return wrapper
