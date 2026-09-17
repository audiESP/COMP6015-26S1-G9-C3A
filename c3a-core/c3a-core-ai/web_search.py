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

# Australian government/health-authority and established clinical-education
# domains. Results from this set are fetched with a dedicated, scoped Tavily
# call so relevance is judged *within* this trusted set rather than by
# reordering a general search by domain suffix (which promotes irrelevant
# pages just because they happen to sit on a .gov host).
TRUSTED_AU_DOMAINS = [
    "healthdirect.gov.au",
    "health.gov.au",
    "agedcarequality.gov.au",
    "safetyandquality.gov.au",
    "nhmrc.gov.au",
    "resus.org.au",
    "anzcor.org",
    "redcross.org.au",
    "dementia.org.au",
    "nps.org.au",
    "betterhealth.vic.gov.au",
    "healthywa.wa.gov.au",
    "carersaustralia.com.au",
    "palliativecare.org.au",
    "agedcare.royalcommission.gov.au",
]

# Tavily returns a per-result relevance score (roughly 0-1). The trusted-domain
# pass is scoped to a small curated site list, so when none of those sites
# actually cover the topic, Tavily still returns its "least bad" match instead
# of nothing. A score floor rejects those forced/weak matches instead of
# surfacing an authoritative-but-irrelevant page (e.g. a resuscitation
# guideline forced to match a routine medication-documentation query).
MIN_TRUSTED_SCORE = float(os.getenv("TAVILY_TRUSTED_MIN_SCORE", "0.3"))
MIN_GENERAL_SCORE = float(os.getenv("TAVILY_GENERAL_MIN_SCORE", "0.2"))


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

        seen_keys: set[str] = set()
        results: list[WebSearchResult] = []

        # Pass 1: search only trusted AU/health-authority domains. Tavily
        # ranks relevance *within* this scope, so a result only appears if
        # it's actually relevant to the query, not merely on a trusted host.
        trusted = await self._raw_search(
            query,
            max_results=max_results,
            include_domains=TRUSTED_AU_DOMAINS,
            min_score=MIN_TRUSTED_SCORE,
        )
        for item in trusted:
            self._add_unique(item, results, seen_keys)
            if len(results) >= max_results:
                return results

        # Pass 2: general web search to fill any remaining slots, in
        # Tavily's own relevance order (no domain-based reordering).
        remaining = max_results - len(results)
        general = await self._raw_search(query, max_results=remaining + 2, min_score=MIN_GENERAL_SCORE)
        for item in general:
            self._add_unique(item, results, seen_keys)
            if len(results) >= max_results:
                break

        return results

    @staticmethod
    def _add_unique(item: WebSearchResult, results: list[WebSearchResult], seen_keys: set[str]) -> None:
        key = _dedupe_key(item.url)
        if key in seen_keys:
            return
        seen_keys.add(key)
        results.append(item)

    async def _raw_search(
        self,
        query: str,
        max_results: int,
        include_domains: list[str] | None = None,
        min_score: float = 0.0,
    ) -> list[WebSearchResult]:
        if max_results <= 0:
            return []
        payload_body: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "exclude_domains": EXCLUDED_DOMAINS,
        }
        if include_domains:
            payload_body["include_domains"] = include_domains
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(TAVILY_SEARCH_URL, json=payload_body)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning(
                "Tavily web search failed query_preview=%r scoped=%s error=%s",
                query[:120],
                bool(include_domains),
                exc,
                exc_info=True,
            )
            return []

        results = []
        for item in payload.get("results", []):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            snippet = (item.get("content") or "").strip()
            score = item.get("score")
            if not url or not title:
                continue
            if isinstance(score, (int, float)) and score < min_score:
                continue
            results.append(WebSearchResult(title=title, url=url, snippet=snippet))
        return results

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.is_configured,
            "provider": "tavily",
            "last_error": self._last_error,
        }


def _dedupe_key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.hostname or ''}{parts.path.rstrip('/')}".lower()
