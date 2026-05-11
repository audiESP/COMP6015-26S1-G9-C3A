"""Database connectivity helpers for the C3A Core API."""

from __future__ import annotations

import logging
import os
import time
from urllib.parse import urlsplit

import anyio
import psycopg


logger = logging.getLogger(__name__)


class DatabaseHealthChecker:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "").strip()

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
        with psycopg.connect(self.database_url, connect_timeout=10) as connection:
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
