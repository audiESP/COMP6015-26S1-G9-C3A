"""PDF extraction and chunking for the SilverCare knowledge base."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from .config import DEFAULT_LANGUAGE


TARGET_WORDS = 450
OVERLAP_WORDS = 80

DOC_TYPE_BY_FILENAME = {
    "delirium_clinical_care_standard_2021.pdf": "clinical_guideline",
    "quality-standards-guidance-resource-sep22.pdf": "aged_care_standard",
}

TITLE_BY_FILENAME = {
    "delirium_clinical_care_standard_2021.pdf": "Delirium Clinical Care Standard 2021",
    "quality-standards-guidance-resource-sep22.pdf": (
        "Guidance and Resources for Providers to Support the Aged Care Quality Standards"
    ),
}


@dataclass(frozen=True)
class PdfChunk:
    text: str
    doc_id: str
    source_title: str
    source_filename: str
    source_path: str
    doc_type: str
    language: str
    page_start: int
    page_end: int
    section_heading: str
    chunk_index: int
    content_hash: str
    ingested_at: str

    def to_payload(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    heading: str


def build_pdf_chunks(
    pdf_path: Path,
    doc_type: str | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> list[PdfChunk]:
    pages = extract_pdf_pages(pdf_path)
    if not pages:
        return []

    doc_id = file_hash(pdf_path)
    source_filename = pdf_path.name
    source_title = TITLE_BY_FILENAME.get(source_filename, title_from_filename(pdf_path))
    resolved_doc_type = doc_type or DOC_TYPE_BY_FILENAME.get(source_filename, "clinical_guideline")
    ingested_at = datetime.now(timezone.utc).isoformat()
    chunks: list[PdfChunk] = []

    for index, chunk_data in enumerate(chunk_pages(pages)):
        text = chunk_data["text"]
        chunks.append(
            PdfChunk(
                text=text,
                doc_id=doc_id,
                source_title=source_title,
                source_filename=source_filename,
                source_path=str(pdf_path),
                doc_type=resolved_doc_type,
                language=language,
                page_start=chunk_data["page_start"],
                page_end=chunk_data["page_end"],
                section_heading=chunk_data["section_heading"],
                chunk_index=index,
                content_hash=text_hash(text),
                ingested_at=ingested_at,
            )
        )

    return chunks


def extract_pdf_pages(pdf_path: Path) -> list[PageText]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is not installed. Install backend requirements with "
            "`pip install -r c3a-core-ai/requirements.txt`."
        ) from exc

    reader = PdfReader(str(pdf_path))
    pages: list[PageText] = []
    for index, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        cleaned = clean_page_text(raw_text)
        if not cleaned or should_skip_page(pdf_path.name, index, cleaned):
            continue
        pages.append(
            PageText(
                page_number=index,
                text=cleaned,
                heading=detect_heading(raw_text),
            )
        )
    return pages


def chunk_pages(
    pages: list[PageText],
    target_words: int = TARGET_WORDS,
    overlap_words: int = OVERLAP_WORDS,
) -> list[dict]:
    chunks: list[dict] = []
    current_segments: list[tuple[int, str, str]] = []
    current_word_count = 0

    for page in pages:
        words = page.text.split()
        current_segments.append((page.page_number, page.text, page.heading))
        current_word_count += len(words)
        if current_word_count >= target_words:
            chunks.append(segments_to_chunk(current_segments))
            overlap_text = tail_words(" ".join(segment[1] for segment in current_segments), overlap_words)
            current_segments = (
                [(page.page_number, overlap_text, page.heading)] if overlap_text else []
            )
            current_word_count = len(overlap_text.split())

    if current_segments:
        chunks.append(segments_to_chunk(current_segments))

    return [chunk for chunk in chunks if chunk["text"].strip()]


def segments_to_chunk(segments: list[tuple[int, str, str]]) -> dict:
    text = "\n\n".join(segment[1] for segment in segments if segment[1].strip())
    headings = [segment[2] for segment in segments if segment[2]]
    return {
        "text": text,
        "page_start": min(segment[0] for segment in segments),
        "page_end": max(segment[0] for segment in segments),
        "section_heading": headings[0] if headings else "",
    }


def clean_page_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"-\s*\n\s*", "", text)
    lines = []
    for raw_line in text.splitlines():
        line = normalize_spaces(raw_line)
        if not line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if re.fullmatch(r"Page\s+\d+(\s+of\s+\d+)?", line, flags=re.IGNORECASE):
            continue
        lines.append(line)
    return "\n".join(lines)


def should_skip_page(source_filename: str, page_number: int, text: str) -> bool:
    normalized = normalize_spaces(text).lower()
    if source_filename == "delirium_clinical_care_standard_2021.pdf":
        if page_number <= 4 or page_number >= 42:
            return True
    if source_filename == "quality-standards-guidance-resource-sep22.pdf":
        if page_number <= 3 or page_number >= 191:
            return True
    reference_markers = normalized.count("available from:") + normalized.count(" doi")
    return reference_markers >= 4


def detect_heading(raw_text: str) -> str:
    for raw_line in raw_text.splitlines():
        line = normalize_spaces(raw_line)
        if not line or len(line) > 120:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if line.lower() in {"contents", "copyright"}:
            continue
        if looks_like_heading(line):
            return line
    return ""


def looks_like_heading(line: str) -> bool:
    if line.endswith("."):
        return False
    words = line.split()
    if len(words) > 12:
        return False
    uppercase_words = sum(1 for word in words if word[:1].isupper())
    return uppercase_words >= max(1, len(words) // 2)


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tail_words(text: str, count: int) -> str:
    words = text.split()
    if len(words) <= count:
        return text
    return " ".join(words[-count:])


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_hash(text: str) -> str:
    normalized = normalize_spaces(text).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def title_from_filename(path: Path) -> str:
    words = re.split(r"[-_]+", path.stem)
    return " ".join(word.capitalize() for word in words if word)
