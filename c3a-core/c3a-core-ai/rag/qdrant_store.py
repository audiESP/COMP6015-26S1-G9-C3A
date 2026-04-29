"""Qdrant collection management, ingestion, and retrieval."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from typing import Any

from .citations import RetrievedChunk
from .config import RagSettings, require_qdrant_settings
from .embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


PAYLOAD_INDEXES = {
    "doc_type": "keyword",
    "language": "keyword",
    "source_filename": "keyword",
    "content_hash": "keyword",
}


class QdrantKnowledgeStore:
    def __init__(
        self,
        settings: RagSettings,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.settings = require_qdrant_settings(settings)
        self.embedding_provider = embedding_provider or EmbeddingProvider(
            self.settings.embedding_model
        )

    @property
    def client(self):
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError(
                "qdrant-client is not installed. Install backend requirements with "
                "`pip install -r c3a-core-ai/requirements.txt`."
            ) from exc

        return QdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key,
            timeout=60,
        )

    def ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        client = self.client
        vector_size = self.embedding_provider.dimension
        if client.collection_exists(self.settings.collection_name):
            logger.info("Qdrant collection already exists: %s", self.settings.collection_name)
        else:
            client.create_collection(
                collection_name=self.settings.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info(
                "Created Qdrant collection %s with vector size %s",
                self.settings.collection_name,
                vector_size,
            )

        self._ensure_payload_indexes(client)

    def _ensure_payload_indexes(self, client: Any) -> None:
        from qdrant_client.models import PayloadSchemaType

        schema_map = {
            "keyword": PayloadSchemaType.KEYWORD,
        }
        for field_name, schema_name in PAYLOAD_INDEXES.items():
            try:
                client.create_payload_index(
                    collection_name=self.settings.collection_name,
                    field_name=field_name,
                    field_schema=schema_map[schema_name],
                    wait=True,
                )
            except Exception as exc:  # Qdrant returns an error when the index exists.
                logger.debug("Payload index %s was not created: %s", field_name, exc)

    def upsert_chunks(self, chunks: list[dict[str, Any]], batch_size: int = 32) -> int:
        from qdrant_client.models import PointStruct

        if not chunks:
            return 0

        client = self.client
        total = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = self.embedding_provider.embed_texts(chunk["text"] for chunk in batch)
            points = []
            for chunk, vector in zip(batch, vectors):
                point_id = _stable_point_id(chunk)
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=chunk,
                    )
                )

            client.upsert(
                collection_name=self.settings.collection_name,
                points=points,
                wait=True,
            )
            total += len(points)
            logger.info("Upserted %s/%s chunks", total, len(chunks))
        return total

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        started_at = time.perf_counter()
        vector = self.embedding_provider.embed_texts([query])[0]
        logger.debug(
            "Qdrant search embedded query vector_size=%s elapsed_ms=%.1f",
            len(vector),
            (time.perf_counter() - started_at) * 1000,
        )
        client = self.client
        limit = top_k or self.settings.top_k

        try:
            response = client.query_points(
                collection_name=self.settings.collection_name,
                query=vector,
                limit=limit,
                with_payload=True,
            )
            points = response.points
        except AttributeError:
            points = client.search(
                collection_name=self.settings.collection_name,
                query_vector=vector,
                limit=limit,
                with_payload=True,
            )

        results: list[RetrievedChunk] = []
        for point in points:
            payload = point.payload or {}
            text = str(payload.get("text", "")).strip()
            if not text:
                continue
            results.append(
                RetrievedChunk(
                    text=text,
                    score=float(getattr(point, "score", 0.0)),
                    source_title=str(payload.get("source_title", "Unknown source")),
                    source_filename=str(payload.get("source_filename", "")),
                    page_start=int(payload.get("page_start", 0) or 0),
                    page_end=int(payload.get("page_end", payload.get("page_start", 0)) or 0),
                    section_heading=str(payload.get("section_heading", "")),
                    doc_type=str(payload.get("doc_type", "")),
                )
            )
        logger.info(
            "Qdrant search completed collection=%s limit=%s results=%s elapsed_ms=%.1f",
            self.settings.collection_name,
            limit,
            len(results),
            (time.perf_counter() - started_at) * 1000,
        )
        return results


def chunk_to_payload(chunk: Any) -> dict[str, Any]:
    if hasattr(chunk, "__dataclass_fields__"):
        return asdict(chunk)
    return dict(chunk)


def _stable_point_id(chunk: dict[str, Any]) -> str:
    key = f"{chunk['doc_id']}:{chunk['chunk_index']}:{chunk['content_hash']}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
