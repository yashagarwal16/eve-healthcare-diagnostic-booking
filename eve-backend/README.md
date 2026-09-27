# EVE Healthcare — Diagnostic Booking & Payment Service

A small backend service for booking diagnostic tests at diagnostic centres,
with a simulated (mock) payment flow, built for the EVE Healthcare SDE
Intern backend assignment.

## Stack & why

| Concern       | Choice                          | Why |
|---------------|----------------------------------|-----|
| Framework     | Flask                            | Explicit, minimal magic — good fit for a small, reviewable service |
| Database      | Microsoft SQL Server             | Matches the schema/relational design this assignment calls for |
| DB driver     | `pymssql`                        | Ships prebuilt wheels bundling FreeTDS — no separate ODBC driver install needed on the host or in the Docker image, unlike `pyodbc` |
| Data access   | Raw parameterized SQL (no ORM)   | Keeps the query ↔ schema relationship explicit and easy to reason/explain, at the cost of some boilerplate an ORM would remove |
| Auth          | Hand-rolled `PyJWT` + `werkzeug.security` | A few readable lines instead of a library abstraction — deliberate, so the whole auth flow can be explained end-to-end |
| Tests         | `unittest` (stdlib)              | No extra test-framework dependency |
| Docs          | Hand-written OpenAPI (`docs/openapi.yaml`) | No `flask-swagger-ui` dependency; paste into https://editor.swagger.io to view |
| Logging       | stdlib `logging` + JSON formatter | Structured, greppable logs without a logging framework dependency |

## Project layout

```
eve-backend/
├── app/
│   ├── __init__.py          # Flask app factory, request logging, error handlers
│   ├── config.py            # Env-var driven config
│   ├── db.py                 # pymssql connection + cursor context manager
│   ├── auth.py               # password hashing, JWT issue/verify, @login_required
│   ├── validation.py         # request validation helpers
│   ├── logging_config.py     # structured JSON logging
│   └── routes/
│       ├── auth_routes.py    # /auth/signup, /auth/login
│       ├── centres.py        # /centres, /centres/<id>/tests
│       ├── bookings.py       # /bookings, /bookings/<id>, /bookings/<id>/cancel
│       └── payments.py       # /payments/, /payments/webhook/
├── sql/
│   ├── schema.sql             # DDL: Users, Centres, Tests, Bookings, Payments, PaymentEvents
│   └── seed.sql                # optional sample data
├── scripts/
│   └── init_db.py             # applies schema.sql/seed.sql (SQL Server has no auto-init dir)
├── tests/
│   ├── test_validation.py      # pure unit tests (no DB)
│   ├── test_auth_utils.py      # pure unit tests (no DB)
│   └── test_integration_flow.py # full HTTP flow against a real DB, self-skips if DB is down
├── docs/openapi.yaml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── run.py
```

## How to run locally

### Option A — Docker Compose (recommended)

```bash
docker-compose up -d --build
# wait ~20-30s for the SQL Server healthcheck to pass, then apply the schema:
docker-compose exec api python scripts/init_db.py --seed
```

The API is now at `http://localhost:5000`. Try:

```bash
curl http://localhost:5000/health
```

### Option B — Run locally against a Dockerized DB only

```bash
docker run -d --name eve-mssql -e ACCEPT_EULA=Y \
  -e MSSQL_SA_PASSWORD="YourStrong!Passw0rd" -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

cp .env.example .env      # edit MSSQL_HOST=localhost
pip install -r requirements.txt
python scripts/init_db.py --seed
python run.py
```

### Running tests

```bash
# Pure unit tests, no DB needed:
python -m unittest tests.test_validation tests.test_auth_utils -v

# Full suite, including DB-backed integration tests (needs the DB running + schema applied):
MSSQL_HOST=localhost python -m unittest discover -s tests -v
```

If the DB isn't reachable, the integration tests are skipped (not failed),
so `python -m unittest discover` is always safe to run.

## API endpoints & example requests

Full spec in [`docs/openapi.yaml`](docs/openapi.yaml). Quick tour:

```bash
# Sign up
curl -X POST localhost:5000/auth/signup -H "Content-Type: application/json" \
  -d '{"name":"Yash","email":"yash@example.com","password":"supersecret123"}'
# -> { "id": 1, "token": "<JWT>", ... }

TOKEN="<paste JWT here>"

# List centres + their tests
curl localhost:5000/centres

# Book a test
curl -X POST localhost:5000/bookings -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"test_id":1,"appointment_time":"2026-10-05T14:30:00"}'
# -> { "id": 1, "status": "PENDING", ... }

# Simulate payment
curl -X POST localhost:5000/payments/ -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"booking_id":1}'
# -> booking flips to CONFIRMED or FAILED

# Simulate a provider webhook callback
curl -X POST localhost:5000/payments/webhook/ \
  -H "X-Webhook-Secret: sim-provider-secret" -H "Content-Type: application/json" \
  -d '{"event_id":"evt_123","booking_id":1,"status":"SUCCESS"}'
```

## Database / schema design

```
Users(id, name, email UNIQUE, password_hash, created_at)
Centres(id, name, location, created_at)
Tests(id, centre_id FK→Centres, name, price, created_at)
Bookings(id, user_id FK→Users, test_id FK→Tests, centre_id FK→Centres,
          appointment_time, amount, status, created_at, updated_at)
Payments(id, booking_id FK→Bookings, amount, status, provider_reference, created_at)
PaymentEvents(id, event_id UNIQUE, booking_id FK→Bookings, status, raw_payload, created_at)
```

Key decisions:

- **`Booking.amount` is a price snapshot**, copied from `Test.price` at
  booking time. If a centre later changes a test's price, existing
  bookings keep the amount the user actually agreed to pay.
- **Booking status** is a simple state machine: `PENDING → CONFIRMED` or
  `PENDING → FAILED`, and `PENDING → CANCELLED`. Enforced in application
  code (see `bookings.py` / `payments.py`) rather than DB triggers, so the
  transition logic stays easy to read, test, and explain.
- **Webhook idempotency is a DB-level guarantee, not just an app-level
  check.** `PaymentEvents.event_id` has a `UNIQUE` constraint. The webhook
  handler always attempts an `INSERT`; if it fails with an integrity
  error, that exact event was already processed, and the handler returns
  the previously recorded outcome without touching the booking again.
  This holds even if two copies of the same webhook arrive concurrently —
  the uniqueness is enforced by SQL Server itself, not by a
  check-then-act read in Python, which would have a race window.
- A booking is only ever transitioned out of `PENDING` **once**. If a
  webhook event arrives for a booking that's already `CONFIRMED`,
  `FAILED`, or `CANCELLED`, the event is recorded but the booking is left
  untouched — this stops a late/duplicate/out-of-order webhook from
  flipping an already-settled booking (tested explicitly in
  `test_webhook_does_not_override_already_confirmed_booking`).

## Edge cases handled

- Invalid/missing request fields → `400` with a specific message (`validation.py`)
- Duplicate signup email → `409` (relies on the `Users.email` unique constraint)
- Wrong password / unknown email at login → identical `401` for both, so the
  endpoint doesn't leak which emails are registered
- Booking a non-existent test → `404`
- Viewing or cancelling another user's booking → `403`
- Paying for a booking that isn't `PENDING` (already paid/cancelled) → `409`
- Cancelling a booking that's already `CONFIRMED`/`CANCELLED` → `409`
- Repeated webhook delivery of the same event → idempotent no-op (see above)
- Webhook without the correct shared secret → `401`
- Webhook for a non-existent booking → `404`
- Unknown routes / wrong HTTP method → clean JSON `404`/`405` (not Flask's HTML default)
- Any unhandled server exception → logged with stack trace, generic `500` returned to the client (no internals leaked)

## Assumptions made

- Any authenticated user can register a centre / add a test to it (no
  admin/staff role). A real system would add role-based access control
  here — called out as a simplification, not an oversight.
- The synchronous `POST /payments/` endpoint and the async
  `POST /payments/webhook/` endpoint are treated as two different ways the
  *same* real-world event could reach the system (a gateway that resolves
  inline vs. one that call back later). Both update the booking, but the
  webhook additionally guards against replay.
- Pagination is offset-based (`page`/`page_size`) rather than cursor-based,
  which is simpler and sufficient at this scale.
- The webhook's shared-secret header is a simplified stand-in for real
  signature verification (e.g. HMAC over the raw body, as Stripe/Razorpay
  do) — enough to demonstrate the concept without building a full provider
  simulator.

## What I'd improve with more time

- Real signature-based webhook verification (HMAC) instead of a shared secret header.
- Role-based access control for centre/test management (admin vs. patient).
- Idempotency keys on the booking-creation and payment endpoints too, not just the webhook.
- Rate limiting on `/auth/login` to slow down credential-stuffing attempts.
- Celery + Redis for webhook processing, with retry/backoff, so a slow DB
  write doesn't block the provider's callback response.
- Alembic-style migrations instead of a single `schema.sql`, so schema
  changes are versioned.
- Swagger UI served in-app (`flask-swagger-ui`) rather than a static YAML file.
