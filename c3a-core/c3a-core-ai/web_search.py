"""Tavily-backed web search used to supplement internal training material retrieval."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Video platforms return content that can't be skimmed or cited like an
# article, so they are excluded from a clinical/care-work search.
EXCLUDED_DOMAINS = ["youtube.com", "youtu.be", "tiktok.com", "vimeo.com"]


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


class WebSearchService:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY", "").strip()
        self.timeout_seconds = float(os.getenv("TAVILY_TIMEOUT_SECONDS", "15"))
        self._last_error: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, max_results: int = 3) -> list[WebSearchResult]:
        if not self.is_configured or not query.strip():
            return []
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    TAVILY_SEARCH_URL,
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                        "include_answer": False,
                    },
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Tavily web search failed query_preview=%r error=%s", query[:120], exc, exc_info=True)
            return []

        results = []
        for item in payload.get("results", [])[:max_results]:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            snippet = (item.get("content") or "").strip()
            if not url or not title:
                continue
            results.append(WebSearchResult(title=title, url=url, snippet=snippet))
        return results

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.is_configured,
            "provider": "tavily",
            "last_error": self._last_error,
        }
