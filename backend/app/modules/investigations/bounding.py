"""Fit model inputs to a character budget without breaking structure or meaning.

A plain slice can cut a JSON packet mid-object or drop the end of an article without
telling the model. These helpers trim at sensible boundaries and say what was removed.
"""

from __future__ import annotations

import json

TRUNCATION_NOTE = "\n\n[Text shortened: the rest of this content was not included.]"


def clip_text(text: str, limit: int, *, note: bool = True) -> str:
    """Cut text to at most ``limit`` characters at a paragraph, sentence or word boundary."""
    if len(text) <= limit:
        return text
    suffix = TRUNCATION_NOTE if note else ""
    budget = max(0, limit - len(suffix))
    head = text[:budget]
    for separator in ("\n\n", ". ", "\n", " "):
        cut = head.rfind(separator)
        if cut >= budget * 0.6:
            head = head[: cut + (1 if separator == ". " else 0)]
            break
    return head.rstrip() + suffix


def fit_evidence_packet(packet_json: str, limit: int) -> str:
    """Return a valid JSON packet within ``limit`` characters.

    Shortens the longest excerpts first, then drops the lowest-priority excerpts from the
    end, and records a limitation so the model knows evidence was omitted. Claims are
    never dropped.
    """
    if len(packet_json) <= limit:
        return packet_json
    try:
        packet = json.loads(packet_json)
    except json.JSONDecodeError:
        return clip_text(packet_json, limit)
    evidence = packet.get("evidence")
    if not isinstance(evidence, list):
        return clip_text(packet_json, limit)

    def size() -> int:
        return len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")))

    note = "Some evidence excerpts were shortened or omitted to fit the review budget."
    limitations = packet.setdefault("limitations", [])
    if isinstance(limitations, list) and note not in limitations:
        limitations.append(note)

    # 1. Shorten long excerpts towards 400 characters, longest first.
    while size() > limit:
        longest = max(
            (
                item
                for item in evidence
                if isinstance(item, dict) and isinstance(item.get("excerpt"), str)
            ),
            key=lambda item: len(item["excerpt"]),
            default=None,
        )
        if longest is None or len(longest["excerpt"]) <= 400:
            break
        excess = size() - limit
        target = max(400, len(longest["excerpt"]) - max(excess, 200))
        longest["excerpt"] = clip_text(longest["excerpt"], target, note=False) + " [...]"
    # 2. Drop excerpts from the end; packets are ordered by priority and interleaved by claim.
    while size() > limit and evidence:
        evidence.pop()
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
