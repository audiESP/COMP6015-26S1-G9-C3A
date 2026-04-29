"""Ingest English PDF guideline documents into Qdrant."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from rag.config import get_rag_settings, require_qdrant_settings
from rag.pdf_ingestion import build_pdf_chunks
from rag.qdrant_store import QdrantKnowledgeStore


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest PDF documents into Qdrant.")
    parser.add_argument(
        "--input",
        default="resource",
        help="PDF file or directory containing PDF files.",
    )
    parser.add_argument(
        "--doc-type",
        default=None,
        help="Optional document type override for every imported PDF.",
    )
    return parser.parse_args()


def iter_pdf_paths(input_path: Path) -> list[Path]:
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        return [input_path]
    if input_path.is_dir():
        return sorted(input_path.glob("*.pdf"))
    return []


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    pdf_paths = iter_pdf_paths(input_path)
    if not pdf_paths:
        raise RuntimeError(f"No PDF files found at {input_path}")

    settings = require_qdrant_settings(get_rag_settings())
    store = QdrantKnowledgeStore(settings)
    store.ensure_collection()

    total_chunks = 0
    total_documents = 0
    for pdf_path in pdf_paths:
        logger.info("Extracting PDF: %s", pdf_path)
        chunks = build_pdf_chunks(pdf_path, doc_type=args.doc_type)
        if not chunks:
            logger.warning("Skipped PDF with no extractable text: %s", pdf_path)
            continue

        payloads = [chunk.to_payload() for chunk in chunks]
        upserted = store.upsert_chunks(payloads)
        total_chunks += upserted
        total_documents += 1
        logger.info("Imported %s chunks from %s", upserted, pdf_path.name)

    print(f"Imported {total_chunks} chunks from {total_documents} PDF document(s).")


if __name__ == "__main__":
    main()
