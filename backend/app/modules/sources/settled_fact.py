"""Bounded Wikipedia/Wikidata reference lookup for settled-fact investigations."""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 1_000_000
# Wikimedia asks API clients to identify themselves with a way to contact the operator.
USER_AGENT = (
    "AgentZero/0.2 (https://agent-zero-web.onrender.com; Sinaps Technology fact-checking; "
    "reference lookup)"
)
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
            "User-Agent": USER_AGENT,
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


_SENTENCE = re.compile(r"(?:[^.!?\n]|(?<=\d)\.(?=\d))+[.!?]?")
_TERM = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "was", "were", "for", "with", "that", "this", "from", "are", "has", "had"}


def _terms(text: str) -> set[str]:
    return {word for word in _TERM.findall(text.casefold()) if word not in _STOP}


def best_matching_passage(claim_text: str, article: str, *, sentences: int = 3) -> str | None:
    """Return the run of sentences in the article that shares the most terms with the claim.

    The result is an exact substring of the article, so it can still be validated.
    """
    claim_terms = _terms(claim_text)
    spans = [(m.start(), m.end()) for m in _SENTENCE.finditer(article) if m.group().strip()]
    if not claim_terms or not spans:
        return None
    # Words found all through the article (its own subject, such as "FIFA World Cup")
    # say little about where the claimed fact is; rarer claim words ("won") decide.
    sentence_terms = [_terms(article[start:end]) for start, end in spans]
    count = len(spans)
    weight = {
        term: math.log((count + 1) / (1 + sum(term in terms for terms in sentence_terms))) + 0.1
        for term in claim_terms
    }
    best: tuple[float, int, int] | None = None
    for i in range(len(spans)):
        window = spans[i : i + sentences]
        shared = claim_terms & set().union(
            *sentence_terms[i : i + sentences]
        )
        score = sum(weight[term] for term in shared)
        if best is None or score > best[0]:
            best = (score, window[0][0], window[-1][1])
    if best is None or best[0] == 0:
        return None
    return article[best[1] : best[2]].strip()[:MAX_EXCERPT_CHARS]


def _full_extract(title: str, *, deadline: float) -> str | None:
    params = urlencode(
        {
            "action": "query",
            "prop": "extracts",
            "titles": title[:300],
            "explaintext": "1",
            "exsectionformat": "plain",
            "format": "json",
            "formatversion": "2",
        }
    )
    try:
        result = _request_json(f"https://en.wikipedia.org/w/api.php?{params}", deadline=deadline)
    except (RuntimeError, TimeoutError):
        return None
    pages = (result.get("query") or {}).get("pages") if isinstance(result, dict) else None
    if isinstance(pages, list) and pages and isinstance(pages[0], dict):
        text = pages[0].get("extract")
        return text if isinstance(text, str) else None
    return None


_NAME_TOKEN = re.compile(r"^(?:[A-Z][\w'’.-]*|\d{4})$")
_NOT_NAMES = frozenset({"A", "An", "The", "In", "On", "At", "This", "That", "It", "I"})


def named_phrase(claim_text: str) -> str | None:
    """The longest run of capitalised words or years, e.g. "2022 FIFA World Cup".

    Searching the whole sentence ranks articles that share the claim's other words
    ("Kenya won ...") above the article about the thing the claim is about.
    """
    best: list[str] = []
    run: list[str] = []
    for raw in (claim_text or "").split():
        token = raw.strip(",.;:!?()\"")
        if token and token not in _NOT_NAMES and _NAME_TOKEN.match(token):
            run.append(token)
            if len(run) > len(best):
                best = list(run)
        else:
            run = []
    return " ".join(best) if len(best) >= 2 else None


def _wikipedia_search(query: str, *, limit: int, deadline: float) -> list[dict]:
    params = urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": query[:500],
            "gsrlimit": str(limit),
            "prop": "extracts|info",
            "inprop": "url",
            "explaintext": "1",
            "exintro": "1",
            "exsentences": "4",
            "format": "json",
            "formatversion": "2",
        }
    )
    result = _request_json(f"https://en.wikipedia.org/w/api.php?{params}", deadline=deadline)
    query_result = result.get("query")
    pages = query_result.get("pages", []) if isinstance(query_result, dict) else []
    if not isinstance(pages, list):
        return []
    # Search results arrive unordered; "index" is the search rank.
    return sorted(
        (page for page in pages if isinstance(page, dict)),
        key=lambda page: page.get("index", 99),
    )


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

    try:
        pages = _wikipedia_search(claim_text, limit=3, deadline=deadline)
        phrase = named_phrase(claim_text)
        if phrase and time.monotonic() < deadline - 0.6:
            try:
                named = _wikipedia_search(phrase, limit=1, deadline=deadline)
            except RuntimeError:
                named = []
            # Only an article named after the phrase, not one that merely shares a word
            # ("2019 Kenya" must not put "Kenya Barris" first).
            words = phrase.casefold().split()
            named = [
                page
                for page in named
                if all(word in str(page.get("title", "")).casefold().split() for word in words)
            ]
            titles = {page.get("title") for page in named}
            pages = named + [page for page in pages if page.get("title") not in titles]
        for rank, page in enumerate(pages[:3]):
            if not isinstance(page, dict):
                continue
            excerpt = page.get("extract")
            url = page.get("fullurl")
            title = page.get("title")
            if rank == 0 and isinstance(title, str) and time.monotonic() < deadline - 0.3:
                # The intro often omits the specific fact; read the article and keep the
                # passage that best matches the claim.
                full = _full_extract(title, deadline=deadline)
                if full:
                    excerpt = best_matching_passage(claim_text, full) or excerpt
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
