from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from taxi_bot.config import DATABASE_URL

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "taxi_bot.sqlite3"


class DBConnection:
    def __init__(self, connection: Any, backend: str):
        self._connection = connection
        self.backend = backend

    def __enter__(self) -> "DBConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type:
            self._connection.rollback()
        else:
            self._connection.commit()
        self._connection.close()

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()):
        final_query = self._translate_params(query)
        return self._connection.execute(final_query, params)

    def _translate_params(self, query: str) -> str:
        if self.backend == "postgres":
            return query.replace("?", "%s")
        return query


def _sqlite_connection() -> DBConnection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA synchronous=NORMAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    return DBConnection(connection, backend="sqlite")


def _postgres_connection() -> DBConnection:
    if psycopg is None:
        raise RuntimeError(
            "psycopg is required for DATABASE_URL Postgres connections. "
            "Install dependencies from requirements.txt."
        )

    connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return DBConnection(connection, backend="postgres")


def get_connection() -> DBConnection:
    if DATABASE_URL:
        return _postgres_connection()
    return _sqlite_connection()


def init_db() -> None:
    with get_connection() as connection:
        if connection.backend == "postgres":
            _init_postgres(connection)
        else:
            _init_sqlite(connection)


def _init_sqlite(connection: DBConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS drivers (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            username TEXT DEFAULT '',
            online INTEGER NOT NULL DEFAULT 0,
            busy INTEGER NOT NULL DEFAULT 0,
            latitude REAL,
            longitude REAL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rides (
            ride_id TEXT PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            driver_id INTEGER,
            pickup_lat REAL NOT NULL,
            pickup_lon REAL NOT NULL,
            drop_lat REAL NOT NULL,
            drop_lon REAL NOT NULL,
            distance_km REAL NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(driver_id) REFERENCES drivers(user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            ticket_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS driver_access (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            username TEXT DEFAULT '',
            created_by_admin INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS booking_cancellations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ride_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_id TEXT NOT NULL,
            driver_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'offered',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            responded_at TEXT,
            UNIQUE(ride_id, driver_id),
            FOREIGN KEY(ride_id) REFERENCES rides(ride_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ride_rejections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_id TEXT NOT NULL,
            driver_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ride_id, driver_id),
            FOREIGN KEY(ride_id) REFERENCES rides(ride_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ride_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_id TEXT NOT NULL,
            reviewer_id INTEGER NOT NULL,
            reviewee_id INTEGER NOT NULL,
            reviewer_role TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ride_id, reviewer_id),
            FOREIGN KEY(ride_id) REFERENCES rides(ride_id)
        )
        """
    )


def _init_postgres(connection: DBConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS drivers (
            user_id BIGINT PRIMARY KEY,
            full_name TEXT NOT NULL,
            username TEXT DEFAULT '',
            online INTEGER NOT NULL DEFAULT 0,
            busy INTEGER NOT NULL DEFAULT 0,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rides (
            ride_id TEXT PRIMARY KEY,
            customer_id BIGINT NOT NULL,
            driver_id BIGINT,
            pickup_lat DOUBLE PRECISION NOT NULL,
            pickup_lon DOUBLE PRECISION NOT NULL,
            drop_lat DOUBLE PRECISION NOT NULL,
            drop_lon DOUBLE PRECISION NOT NULL,
            distance_km DOUBLE PRECISION NOT NULL,
            total_amount DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(driver_id) REFERENCES drivers(user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            ticket_id TEXT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS driver_access (
            user_id BIGINT PRIMARY KEY,
            full_name TEXT NOT NULL,
            username TEXT DEFAULT '',
            created_by_admin BIGINT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS booking_cancellations (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ride_offers (
            id BIGSERIAL PRIMARY KEY,
            ride_id TEXT NOT NULL,
            driver_id BIGINT NOT NULL,
            status TEXT NOT NULL DEFAULT 'offered',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            responded_at TIMESTAMPTZ,
            UNIQUE(ride_id, driver_id),
            FOREIGN KEY(ride_id) REFERENCES rides(ride_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ride_rejections (
            id BIGSERIAL PRIMARY KEY,
            ride_id TEXT NOT NULL,
            driver_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ride_id, driver_id),
            FOREIGN KEY(ride_id) REFERENCES rides(ride_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ride_feedback (
            id BIGSERIAL PRIMARY KEY,
            ride_id TEXT NOT NULL,
            reviewer_id BIGINT NOT NULL,
            reviewee_id BIGINT NOT NULL,
            reviewer_role TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ride_id, reviewer_id),
            FOREIGN KEY(ride_id) REFERENCES rides(ride_id)
        )
        """
    )
