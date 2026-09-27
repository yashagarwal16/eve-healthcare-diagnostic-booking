import os


class Config:
    """
    Centralised config, read from environment variables so the same code
    runs unchanged locally, in Docker, and in CI.
    """

    MSSQL_HOST = os.environ.get("MSSQL_HOST", "localhost")
    MSSQL_PORT = int(os.environ.get("MSSQL_PORT", "1433"))
    MSSQL_USER = os.environ.get("MSSQL_USER", "sa")
    MSSQL_PASSWORD = os.environ.get("MSSQL_PASSWORD", "YourStrong!Passw0rd")
    MSSQL_DB = os.environ.get("MSSQL_DB", "eve_healthcare")

    JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY_MINUTES = int(os.environ.get("JWT_EXPIRY_MINUTES", "60"))

    # Simulated payment gateway success rate (0.0 - 1.0). Kept configurable
    # so tests can force deterministic SUCCESS/FAILED outcomes.
    PAYMENT_SUCCESS_RATE = float(os.environ.get("PAYMENT_SUCCESS_RATE", "0.8"))
