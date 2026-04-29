"""Create or validate the SilverCare Qdrant collection."""

from __future__ import annotations

import logging

from rag.config import get_rag_settings, require_qdrant_settings
from rag.qdrant_store import QdrantKnowledgeStore


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> None:
    settings = require_qdrant_settings(get_rag_settings())
    store = QdrantKnowledgeStore(settings)
    store.ensure_collection()
    print(f"Qdrant collection is ready: {settings.collection_name}")


if __name__ == "__main__":
    main()
