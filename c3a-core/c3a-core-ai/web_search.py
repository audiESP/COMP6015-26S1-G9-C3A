"""Tavily-backed web search used to supplement internal training material retrieval."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Results are only taken from these sites. Unscoped web search returned
# off-topic pages (dictionaries, airport security, workplace lunch blogs), so
# nothing outside this list is ever shown.
TRUSTED_DOMAINS = [
    "agedcarequality.gov.au",
    "health.gov.au",
    "safetyandquality.gov.au",
    "healthdirect.gov.au",
    "betterhealth.vic.gov.au",
    "healthywa.wa.gov.au",
    "health.vic.gov.au",
    "aihw.gov.au",
    "nhmrc.gov.au",
    "nps.org.au",
    "dementia.org.au",
    "carersaustralia.com.au",
    "anmf.org.au",
    "palliativecare.org.au",
    "resus.org.au",
    "anzcor.org",
    "agedcare.royalcommission.gov.au",
]

MIN_TRUSTED_SCORE = float(os.getenv("TAVILY_TRUSTED_MIN_SCORE", "0.3"))

# Trusted domains also host policy pages written for providers and regulators
# (ministerial media releases, compliance, quality standards, submissions).
# They match task topics well but give a care worker nothing to act on during
# a visit, so URLs containing these fragments are dropped.
EXCLUDED_URL_FRAGMENTS = (
    "/ministers/",
    "/media/",
    "/news/",
    "regulation",
    "compliance",
    "/providers/",
    "/strengthened-quality-standards/",
    "/national-standards/",
    "/residential-aged-care/",
    "for-racs",
    "submission",
    "campaign",
    "position-statement",
    "program-manual",
    "scheme-guidelines",
    "aihw.gov.au/reports/",
)

# Search queries phrased as "signs/symptoms + older people" return practical
# observation guidance; queries phrased around the task or the worker ("check",
# "for aged care home visits") return policy pages. Each topic is matched by
# keywords in the task label and detail, in this priority order.
TOPIC_QUERIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("hydration", "nutrition", "dehydrat", "malnutrition"), "signs of dehydration and malnutrition in older people"),
    (("appetite", "meal", "lunch", "eating"), "eating difficulties and loss of appetite in older people tips"),
    (("swallow",), "swallowing difficulty signs in older people"),
    (("confusion", "orientation", "orient", "delirium"), "signs of delirium and sudden confusion in older people"),
    (("pain", "dizziness", "dizzy"), "pain and dizziness warning signs in older people"),
    (("fall", "gait", "walker", "steady", "steadiness"), "preventing falls in older people at home walking aids"),
    (("transfer",), "helping an older person stand up from a chair or bed safely"),
    (("medication", "medicine"), "medication safety and adverse effects in older people at home"),
    (("interpreter", "communication"), "communicating with older people from culturally diverse backgrounds"),
    (("escalation", "unusual symptoms", "deteriorat"), "recognising and reporting deterioration in older people"),
)

# Used when no topic keyword matches, and always for task types whose details
# mention other topics only in passing (a summary that records "nutrition" is
# not a nutrition check).
TYPE_QUERIES = {
    "arrival": "communicating with older people from culturally diverse backgrounds",
    "documentation": "recognising and reporting deterioration in older people",
    "meal": "eating difficulties and loss of appetite in older people tips",
    "medication": "medication safety and adverse effects in older people at home",
    "mobility": "preventing falls in older people at home walking aids",
    "wellbeing": "signs of dehydration and malnutrition in older people",
}
TYPE_ONLY_TASK_TYPES = {"arrival", "documentation"}
MAX_TASK_QUERIES = 2

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()
RELEVANCE_TIMEOUT_SECONDS = float(os.getenv("TASK_MATERIALS_RELEVANCE_TIMEOUT_SECONDS", "60"))

RELEVANCE_PROMPT = """A home care worker is doing this task while visiting an older person at home: {task}
Web page title: {title}
Excerpt: {snippet}

Would this page help the worker recognise warning signs, or decide what to do or report, during the visit? Answer NO if it is mainly about regulation, compliance, funding, provider obligations, policy, or running a residential facility. Reply YES or NO only."""


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

    async def search(self, queries: list[str], task_context: str, max_results: int = 3) -> list[WebSearchResult]:
        queries = [query for query in queries if query.strip()]
        if not self.is_configured or not queries:
            return []

        per_query = await asyncio.gather(
            *(self._trusted_search(query, max_results=max_results * 2) for query in queries)
        )
        candidates = [item for item in _interleave(per_query) if not _is_excluded_url(item.url)]
        if not candidates:
            return []

        verdicts = await asyncio.gather(
            *(self._is_relevant(task_context, item) for item in candidates)
        )
        kept: list[WebSearchResult] = []
        seen_keys: set[str] = set()
        for item, relevant in zip(candidates, verdicts):
            if not relevant:
                continue
            key = _dedupe_key(item.url)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            kept.append(item)
            if len(kept) >= max_results:
                break
        return kept

    async def _trusted_search(self, query: str, max_results: int) -> list[WebSearchResult]:
        payload_body: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "chunks_per_source": 2,
            "include_answer": False,
            "include_domains": TRUSTED_DOMAINS,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(TAVILY_SEARCH_URL, json=payload_body)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Tavily web search failed query_preview=%r error=%s", query[:120], exc, exc_info=True)
            return []

        results = []
        for item in payload.get("results", []):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            score = item.get("score")
            if not url or not title:
                continue
            if isinstance(score, (int, float)) and score < MIN_TRUSTED_SCORE:
                continue
            results.append(WebSearchResult(title=title, url=url, snippet=_clean_snippet(item.get("content") or "")))
        return results

    async def _is_relevant(self, task_context: str, item: WebSearchResult) -> bool:
        prompt = RELEVANCE_PROMPT.format(task=task_context, title=item.title, snippet=item.snippet)
        try:
            async with httpx.AsyncClient(timeout=RELEVANCE_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": OLLAMA_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {"temperature": 0, "num_predict": 5},
                    },
                )
                response.raise_for_status()
                answer = response.json()["message"]["content"].strip().upper()
        except Exception as exc:
            logger.warning("Relevance check failed url=%s error=%s", item.url, exc)
            return False
        return answer.startswith("YES")

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.is_configured,
            "provider": "tavily",
            "last_error": self._last_error,
        }


SNIPPET_MAX_CHARS = 500


def _clean_snippet(text: str) -> str:
    cleaned = re.sub(r"(?m)^#{1,6}\s*", "", text.replace("[...]", " "))
    compact = " ".join(cleaned.split())
    if len(compact) <= SNIPPET_MAX_CHARS:
        return compact
    cut = compact[:SNIPPET_MAX_CHARS]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end > SNIPPET_MAX_CHARS // 2:
        return cut[: end + 1]
    return cut.rstrip() + "..."


def build_task_queries(label: str, detail: str | None = None, task_type: str | None = None) -> list[str]:
    """Return up to MAX_TASK_QUERIES symptom-oriented web queries for a care task."""
    normalized_type = (task_type or "").strip().lower()
    queries: list[str] = []
    if normalized_type not in TYPE_ONLY_TASK_TYPES:
        text = f"{label} {detail or ''}".lower()
        for keywords, query in TOPIC_QUERIES:
            if query not in queries and any(keyword in text for keyword in keywords):
                queries.append(query)
            if len(queries) >= MAX_TASK_QUERIES:
                return queries
    if not queries and normalized_type in TYPE_QUERIES:
        queries.append(TYPE_QUERIES[normalized_type])
    if not queries and label.strip():
        queries.append(f"{label.strip()} older people at home")
    return queries


def _interleave(result_lists: list[list[WebSearchResult]]) -> list[WebSearchResult]:
    # Alternate between queries so one topic's results don't crowd out the other.
    merged: list[WebSearchResult] = []
    for rank in range(max((len(results) for results in result_lists), default=0)):
        merged.extend(results[rank] for results in result_lists if rank < len(results))
    return merged


def _is_excluded_url(url: str) -> bool:
    lowered = url.lower()
    return any(fragment in lowered for fragment in EXCLUDED_URL_FRAGMENTS)


def _dedupe_key(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}".lower()
