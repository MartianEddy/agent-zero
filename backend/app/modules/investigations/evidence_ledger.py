"""Deterministic evidence identity, quote validation, and sentence citation checks."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

CONFIG = Path(__file__).parents[1] / "sources" / "evidence_ledger.json"


def _config() -> dict[str, object]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _norm(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def canonical_domain(url_or_domain: str | None) -> str:
    value = (url_or_domain or "").strip()
    host = (urlsplit(value).hostname if "://" in value else value) or ""
    host = host.casefold().removeprefix("www.").rstrip(".")
    labels = host.split(".")
    if len(labels) >= 3 and labels[-2] in {"co", "go", "ac", "or", "gov"}:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) > 1 else host


def validate_excerpt(excerpt: str, retrieved_text: str) -> tuple[bool, int | None, int | None]:
    """Return original-text offsets for a whitespace-normalized exact excerpt match."""
    if not excerpt or not retrieved_text:
        return False, None, None
    normalized_parts: list[str] = []
    source_offsets: list[int] = []
    in_space = False
    for index, char in enumerate(retrieved_text):
        if char.isspace():
            if not in_space:
                normalized_parts.append(" ")
                source_offsets.append(index)
            in_space = True
        else:
            normalized_parts.append(char.casefold())
            source_offsets.append(index)
            in_space = False
    normalized_text = "".join(normalized_parts).strip()
    normalized_excerpt = " ".join(excerpt.casefold().split())
    start_normalized = normalized_text.find(normalized_excerpt)
    if start_normalized < 0 or not normalized_excerpt:
        return False, None, None
    end_normalized = start_normalized + len(normalized_excerpt)
    return True, source_offsets[start_normalized], source_offsets[end_normalized - 1] + 1


def staleness_flag(
    published_date: str | None, claim_type: str, *, reference_date: date
) -> bool | None:
    """Flag statistical comparisons older than a year; leave unparseable dates unknown."""
    if claim_type != "STATISTICAL" or not published_date:
        return None
    try:
        published = datetime.fromisoformat(published_date.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            published = date.fromisoformat(published_date[:10])
        except ValueError:
            return None
    return published < reference_date - timedelta(days=365)


def independence_groups(items: list[dict[str, str | None]]) -> dict[str, str]:
    """Group syndicated copies by publisher/domain, wire markers, then excerpt similarity."""
    cfg = _config()
    threshold = float(cfg.get("near_duplicate_similarity", 0.9))
    wire_markers = [str(item).casefold() for item in cfg.get("wire_service_markers", [])]
    parent = {str(item["id"]): str(item["id"]) for item in items}

    def root(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(a: str, b: str) -> None:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    owners: dict[str, str] = {}
    wires: dict[str, str] = {}
    for item in items:
        key = str(item["id"])
        domain = canonical_domain(str(item.get("url") or item.get("domain") or ""))
        publisher = _norm(str(item.get("publisher") or ""))
        for identity in {value for value in (publisher, domain) if value}:
            union(key, owners.setdefault(identity, key))
        combined = " ".join(
            str(item.get(field) or "") for field in ("publisher", "title", "excerpt")
        ).casefold()
        for marker in wire_markers:
            if re.search(rf"\b{re.escape(marker)}\b", combined):
                union(key, wires.setdefault(marker, key))
        excerpt = _norm(str(item.get("excerpt") or ""))
        if len(excerpt) >= 40:
            for previous in items:
                previous_key = str(previous["id"])
                if previous_key == key:
                    break
                previous_excerpt = _norm(str(previous.get("excerpt") or ""))
                if (
                    previous_excerpt
                    and SequenceMatcher(None, excerpt, previous_excerpt).ratio() >= threshold
                ):
                    union(key, previous_key)
    roots = {key: f"source-group:{root(key)}" for key in parent}
    return roots


def validate_sentence_citations(
    sentences: list[dict[str, object]], evidence_by_id: dict[str, dict[str, object]], *, run_id: str
) -> tuple[list[dict[str, object]], bool]:
    """Keep sentences whose citations resolve to validated retrieved evidence in this run."""
    accepted: list[dict[str, object]] = []
    dropped = False
    for item in sentences:
        text = str(item.get("sentence") or "").strip()
        ids = item.get("evidence_ids")
        valid = (
            isinstance(ids, list)
            and bool(ids)
            and all(
                str(evidence_id) in evidence_by_id
                and (
                    evidence_by_id[str(evidence_id)].get("retrieved_url")
                    or evidence_by_id[str(evidence_id)].get("is_media")
                )
                and evidence_by_id[str(evidence_id)].get("excerpt_validated") is True
                and str(evidence_by_id[str(evidence_id)].get("run_id")) == run_id
                for evidence_id in ids
            )
        )
        if text and valid:
            accepted.append({"sentence": text, "evidence_ids": [str(value) for value in ids]})
        else:
            dropped = True
    return accepted, dropped
