import logging
import time
import uuid

from flask import Flask, request, g, jsonify

from app.logging_config import configure_logging
from app.routes.auth_routes import auth_bp
from app.routes.centres import centres_bp
from app.routes.bookings import bookings_bp
from app.routes.payments import payments_bp

logger = logging.getLogger("eve.app")


def create_app() -> Flask:
    configure_logging()
    app = Flask(__name__)

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(centres_bp, url_prefix="/centres")
    app.register_blueprint(bookings_bp, url_prefix="/bookings")
    app.register_blueprint(payments_bp, url_prefix="/payments")

    @app.before_request
    def _start_timer():
        g._request_id = str(uuid.uuid4())[:8]
        g._start_time = time.time()

    @app.after_request
    def _log_request(response):
        duration_ms = round((time.time() - g.get("_start_time", time.time())) * 1000, 2)
        logger.info(
            "request completed",
            extra={
                "path": request.path,
                "status_code": response.status_code,
            },
        )
        response.headers["X-Request-Id"] = g.get("_request_id", "")
        return response

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify(error="Resource not found"), 404

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("unhandled server error")
        return jsonify(error="Internal server error"), 500

    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    return app
