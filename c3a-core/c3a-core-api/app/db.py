"""Database connectivity helpers for the C3A Core API."""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import anyio
import psycopg
from psycopg.rows import dict_row

try:
    from psycopg_pool import ConnectionPool
except ImportError:  # pragma: no cover - supports envs before requirements are installed.
    ConnectionPool = None


logger = logging.getLogger(__name__)

_pool = None


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def open_database_pool() -> None:
    global _pool
    url = database_url()
    if not url:
        logger.info("Database pool not opened because DATABASE_URL is not configured")
        return
    if ConnectionPool is None:
        logger.warning("psycopg_pool is not installed; falling back to per-request connections")
        return
    if _pool is not None:
        return

    _pool = ConnectionPool(
        conninfo=url,
        min_size=int(os.getenv("DATABASE_POOL_MIN_SIZE", "1")),
        max_size=int(os.getenv("DATABASE_POOL_MAX_SIZE", "5")),
        timeout=float(os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "10")),
        kwargs={"row_factory": dict_row},
        check=ConnectionPool.check_connection,
        open=True,
    )
    logger.info(
        "Database pool opened min_size=%s max_size=%s",
        os.getenv("DATABASE_POOL_MIN_SIZE", "1"),
        os.getenv("DATABASE_POOL_MAX_SIZE", "5"),
    )


def close_database_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("Database pool closed")


@contextmanager
def get_database_connection(row_factory=dict_row):
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")

    if _pool is not None:
        with _pool.connection() as connection:
            yield connection
        return

    with psycopg.connect(url, row_factory=row_factory, connect_timeout=10) as connection:
        yield connection


class DatabaseHealthChecker:
    def __init__(self):
        self.database_url = database_url()

    @property
    def configured(self) -> bool:
        return bool(self.database_url)

    async def health(self) -> dict[str, str]:
        if not self.database_url:
            return {"status": "not_configured"}

        started_at = time.perf_counter()
        try:
            await anyio.to_thread.run_sync(self._check_connection)
            logger.info(
                "Database health completed configured=%s elapsed_ms=%.1f",
                self.configured,
                (time.perf_counter() - started_at) * 1000,
            )
            return {"status": "ok"}
        except Exception as exc:
            safe_error = _safe_error_message(exc, self.database_url)
            logger.warning(
                "Database health failed configured=%s elapsed_ms=%.1f error=%s",
                self.configured,
                (time.perf_counter() - started_at) * 1000,
                safe_error,
                exc_info=True,
            )
            return {
                "status": "unavailable",
                "error": safe_error,
            }

    def _check_connection(self) -> None:
        with get_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()


def _safe_error_message(exc: Exception, database_url: str) -> str:
    message = str(exc)
    if database_url and database_url in message:
        message = message.replace(database_url, "[DATABASE_URL]")

    parsed = urlsplit(database_url)
    if parsed.password:
        message = message.replace(parsed.password, "[PASSWORD]")
    if parsed.query:
        message = message.replace(parsed.query, "[QUERY]")

    return message[:500]
