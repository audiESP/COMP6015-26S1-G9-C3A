"""Runtime retrieval wrapper used by the chat endpoint."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .citations import RetrievedChunk
from .config import env_file_candidates, get_rag_settings
from .qdrant_store import QdrantKnowledgeStore

logger = logging.getLogger(__name__)


class RagRetriever:
    def __init__(self):
        self.settings = get_rag_settings()
        self._store: QdrantKnowledgeStore | None = None
        self._last_error: str | None = None

    @property
    def is_configured(self) -> bool:
        return self.settings.is_configured

    @property
    def store(self) -> QdrantKnowledgeStore:
        if self._store is None:
            self._store = QdrantKnowledgeStore(self.settings)
        return self._store

    async def retrieve(self, query: str) -> list[RetrievedChunk]:
        if not query.strip() or not self.is_configured:
            logger.info(
                "RAG retrieval skipped configured=%s query_chars=%s",
                self.is_configured,
                len(query.strip()),
            )
            return []

        loop = asyncio.get_event_loop()
        started_at = time.perf_counter()
        try:
            logger.info(
                "RAG retrieval started collection=%s top_k=%s query_preview=%r",
                self.settings.collection_name,
                self.settings.top_k,
                _preview(query),
            )
            results = await loop.run_in_executor(None, self.store.search, query, self.settings.top_k)
            self._last_error = None
            logger.info(
                "RAG retrieval completed results=%s elapsed_ms=%.1f",
                len(results),
                (time.perf_counter() - started_at) * 1000,
            )
            return results
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning(
                "RAG retrieval failed elapsed_ms=%.1f error=%s",
                (time.perf_counter() - started_at) * 1000,
                exc,
                exc_info=True,
            )
            return []

    def close(self) -> None:
        if self._store is not None:
            self._store.close()

    def status(self) -> dict[str, Any]:
        status = "configured" if self.is_configured else "unavailable"
        if self._last_error:
            status = "unavailable"
        return {
            "status": status,
            "configured": self.is_configured,
            "qdrant_url_configured": bool(self.settings.qdrant_url),
            "qdrant_api_key_configured": bool(self.settings.qdrant_api_key),
            "collection": self.settings.collection_name,
            "embedding_model": self.settings.embedding_model,
            "top_k": self.settings.top_k,
            "last_error": self._last_error,
            "env_files_checked": [
                str(path)
                for path in env_file_candidates()
            ],
        }


def _preview(text: str, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."
