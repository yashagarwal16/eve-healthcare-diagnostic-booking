"""
Thin data-access layer over pymssql.

Deliberately not using an ORM: every query is explicit, parameterized SQL
(using pymssql's %s placeholders, which it converts to the correct
SQL Server wire format). This keeps the schema/query relationship visible
and easy to reason about and explain -- at the cost of writing a bit more
boilerplate than an ORM would save.
"""

import contextlib
import pymssql

from app.config import Config


def get_connection():
    return pymssql.connect(
        server=Config.MSSQL_HOST,
        port=str(Config.MSSQL_PORT),
        user=Config.MSSQL_USER,
        password=Config.MSSQL_PASSWORD,
        database=Config.MSSQL_DB,
        as_dict=True,
        autocommit=False,
    )


@contextlib.contextmanager
def get_cursor(commit: bool = False):
    """
    Usage:
        with get_cursor(commit=True) as cur:
            cur.execute("INSERT INTO ...", (a, b))

    Commits only if commit=True and no exception was raised; always closes
    the connection. Rolls back on error so a failed request never leaves a
    half-applied write behind.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
