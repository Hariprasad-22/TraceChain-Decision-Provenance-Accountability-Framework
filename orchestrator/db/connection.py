"""
db/connection.py
----------------
PostgreSQL connection pool for the TraceChain orchestrator.

Uses psycopg2 with a SimpleConnectionPool so every module shares
the same pool instead of opening a new connection per query.

Usage:
    from db.connection import get_conn, release_conn

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(...)
        conn.commit()
    finally:
        release_conn(conn)
"""

import os
from pathlib import Path

import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Load project-root .env, with a fallback for older orchestrator-local copies.
_ENV_CANDIDATES = [
    Path(__file__).resolve().parents[2] / ".env",
    Path(__file__).resolve().parent.parent / ".env",
]
for candidate in _ENV_CANDIDATES:
    if candidate.exists():
        load_dotenv(candidate)
        break

# ─── connection parameters (all from .env) ────────────────────────────────────
_DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME",     "tracechain"),
    "user":     os.getenv("DB_USER",     "tracechain_admin"),
    "password": os.getenv("DB_PASSWORD", "devpassword"),
}

# min/max connections in pool
_MIN_CONN = 1
_MAX_CONN = 10

_pool: pool.SimpleConnectionPool | None = None


def _get_pool() -> pool.SimpleConnectionPool:
    """Lazily create the connection pool on first call."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.SimpleConnectionPool(_MIN_CONN, _MAX_CONN, **_DB_CONFIG)
    return _pool


def get_conn() -> psycopg2.extensions.connection:
    """Borrow a connection from the pool."""
    return _get_pool().getconn()


def release_conn(conn: psycopg2.extensions.connection) -> None:
    """Return a connection back to the pool."""
    _get_pool().putconn(conn)


def close_pool() -> None:
    """Cleanly close the entire pool (call at application shutdown)."""
    global _pool
    if _pool and not _pool.closed:
        _pool.closeall()
        _pool = None
