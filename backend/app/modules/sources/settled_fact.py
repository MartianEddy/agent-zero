"""Bounded Wikipedia/Wikidata reference lookup for settled-fact investigations."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 1_000_000
MAX_EXCERPT_CHARS = 1_500
PER_REQUEST_TIMEOUT_SECONDS = 1.8


@dataclass(frozen=True)
class ReferenceExcerpt:
    title: str
    url: str
    excerpt: str
    provider: str
    stance: str


@dataclass(frozen=True)
class SettledReferenceResult:
    excerpts: list[ReferenceExcerpt]
    unavailable: list[str]
    elapsed_seconds: float


def _request_json(url: str, *, deadline: float) -> dict[str, object]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("reference lookup deadline reached")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "AgentZero/0.1 (settled fact reference lookup)",
        },
    )
    try:
        with urlopen(request, timeout=min(PER_REQUEST_TIMEOUT_SECONDS, remaining)) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("reference provider request failed") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise RuntimeError("reference provider response exceeded the size limit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("reference provider returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("reference provider returned an invalid response")
    return value


def lookup_settled_fact(
    claim_text: str,
    *,
    deadline_seconds: float = 4.5,
) -> SettledReferenceResult:
    """Fetch bounded reference context; Wikidata is context only, never proof by itself."""
    started = time.monotonic()
    deadline = started + min(max(deadline_seconds, 0.1), 4.8)
    excerpts: list[ReferenceExcerpt] = []
    unavailable: list[str] = []

    wikipedia_params = urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": claim_text[:500],
            "gsrlimit": "3",
            "prop": "extracts|info",
            "inprop": "url",
            "explaintext": "1",
            "exsentences": "4",
            "format": "json",
            "formatversion": "2",
        }
    )
    wikipedia_url = f"https://en.wikipedia.org/w/api.php?{wikipedia_params}"
    try:
        result = _request_json(wikipedia_url, deadline=deadline)
        query = result.get("query")
        pages = query.get("pages", []) if isinstance(query, dict) else []
        if not isinstance(pages, list):
            pages = []
        for page in pages[:3]:
            if not isinstance(page, dict):
                continue
            excerpt = page.get("extract")
            url = page.get("fullurl")
            title = page.get("title")
            if isinstance(excerpt, str) and excerpt.strip() and isinstance(url, str):
                excerpts.append(
                    ReferenceExcerpt(
                        title=str(title or "Wikipedia article")[:300],
                        url=url[:2_000],
                        excerpt=excerpt.strip()[:MAX_EXCERPT_CHARS],
                        provider="wikipedia_api",
                        stance="CONTEXT",
                    )
                )
        if not excerpts:
            unavailable.append("Wikipedia returned no matching article text.")
    except RuntimeError:
        unavailable.append("Wikipedia reference lookup failed or timed out.")

    if time.monotonic() < deadline:
        wikidata_params = urlencode(
            {
                "action": "wbsearchentities",
                "search": claim_text[:300],
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": "2",
                "format": "json",
            }
        )
        wikidata_url = f"https://www.wikidata.org/w/api.php?{wikidata_params}"
        try:
            result = _request_json(wikidata_url, deadline=deadline)
            items = result.get("search", [])
            if isinstance(items, list):
                for item in items[:2]:
                    if not isinstance(item, dict):
                        continue
                    description = item.get("description")
                    item_url = item.get("concepturi")
                    label = item.get("label")
                    if isinstance(description, str) and description.strip() and isinstance(item_url, str):
                        excerpts.append(
                            ReferenceExcerpt(
                                title=str(label or "Wikidata item")[:300],
                                url=item_url[:2_000],
                                excerpt=(str(label or "") + ". " + description).strip()[:500],
                                provider="wikidata_api",
                                stance="CONTEXT",
                            )
                        )
        except RuntimeError:
            unavailable.append("Wikidata reference lookup failed or timed out.")
    else:
        unavailable.append("Wikidata reference lookup was not attempted before the case deadline.")

    return SettledReferenceResult(
        excerpts=excerpts,
        unavailable=unavailable,
        elapsed_seconds=time.monotonic() - started,
    )
