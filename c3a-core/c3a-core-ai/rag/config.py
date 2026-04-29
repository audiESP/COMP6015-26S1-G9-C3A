"""Configuration helpers for the Qdrant-backed RAG pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency at import time
    load_dotenv = None


DEFAULT_COLLECTION = "silvercare_knowledge"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_TOP_K = 5
DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True)
class RagSettings:
    qdrant_url: str | None
    qdrant_api_key: str | None
    collection_name: str = DEFAULT_COLLECTION
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    top_k: int = DEFAULT_TOP_K
    language: str = DEFAULT_LANGUAGE

    @property
    def is_configured(self) -> bool:
        return bool(self.qdrant_url and self.qdrant_api_key)


def _load_env_files() -> None:
    if load_dotenv is None:
        return

    for env_path in env_file_candidates():
        load_dotenv(env_path, override=False)


def env_file_candidates() -> list[Path]:
    service_dir = Path(__file__).resolve().parents[1]
    project_dir = service_dir.parent
    legacy_backend_dir = project_dir / "backend"
    cwd = Path.cwd()
    candidates = [
        cwd / ".env",
        service_dir / ".env",
        project_dir / ".env",
        legacy_backend_dir / ".env",
    ]
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_rag_settings() -> RagSettings:
    _load_env_files()
    return RagSettings(
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        collection_name=os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION),
        embedding_model=os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        top_k=_read_int("RAG_TOP_K", DEFAULT_TOP_K),
    )


def require_qdrant_settings(settings: RagSettings | None = None) -> RagSettings:
    resolved = settings or get_rag_settings()
    missing = []
    if not resolved.qdrant_url:
        missing.append("QDRANT_URL")
    if not resolved.qdrant_api_key:
        missing.append("QDRANT_API_KEY")
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required Qdrant configuration: {joined}")
    return resolved
