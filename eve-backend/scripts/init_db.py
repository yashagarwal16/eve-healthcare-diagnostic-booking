"""
Applies sql/schema.sql (and optionally sql/seed.sql) against the configured
SQL Server instance.

Unlike Postgres, the official mssql-server Docker image has no
docker-entrypoint-initdb.d convention, so schema setup is a small explicit
step rather than something docker-compose does for you automatically.

Usage:
    python scripts/init_db.py            # schema only
    python scripts/init_db.py --seed      # schema + sample data
"""

import argparse
import os
import sys
import time

import pymssql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import Config  # noqa: E402


def run_script(path: str, retries: int = 10, delay: int = 3) -> None:
    with open(path, "r") as f:
        sql_text = f.read()

    # SQL Server batches are separated by GO, which is a sqlcmd/SSMS
    # convention, not valid T-SQL -- split on it before executing.
    batches = [b.strip() for b in sql_text.split("GO") if b.strip()]

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            conn = pymssql.connect(
                server=Config.MSSQL_HOST,
                port=str(Config.MSSQL_PORT),
                user=Config.MSSQL_USER,
                password=Config.MSSQL_PASSWORD,
                autocommit=True,
            )
            cur = conn.cursor()
            for batch in batches:
                cur.execute(batch)
            conn.close()
            print(f"Applied {path}")
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[{attempt}/{retries}] DB not ready yet ({e}); retrying in {delay}s...")
            time.sleep(delay)

    raise SystemExit(f"Failed to apply {path}: {last_err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="also load sample data")
    args = parser.parse_args()

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_script(os.path.join(base, "sql", "schema.sql"))
    if args.seed:
        run_script(os.path.join(base, "sql", "seed.sql"))
