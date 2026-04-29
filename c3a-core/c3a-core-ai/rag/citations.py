"""Citation formatting helpers for retrieved guideline chunks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    score: float
    source_title: str
    source_filename: str
    page_start: int
    page_end: int
    section_heading: str = ""
    doc_type: str = ""

    def page_label(self) -> str:
        if self.page_start == self.page_end:
            return f"p. {self.page_start}"
        return f"pp. {self.page_start}-{self.page_end}"

    def citation(self) -> str:
        section = f', "{self.section_heading}"' if self.section_heading else ""
        return f"{self.source_title}{section}, {self.page_label()}"


def dedupe_citations(chunks: list[RetrievedChunk]) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for chunk in chunks:
        citation = chunk.citation()
        if citation in seen:
            continue
        seen.add(citation)
        citations.append(citation)
    return citations
