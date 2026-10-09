"""OpenAI Responses web-search adapter that returns candidates, not findings."""

from dataclasses import dataclass
from typing import Any

class OpenAIWebSearchError(RuntimeError):
    """Raised when the hosted web-search request cannot produce a usable response."""


@dataclass(frozen=True)
class OpenAIWebSearchResponse:
    request_id: str | None
    results: list[dict[str, object]]
    citations: list[dict[str, object]]


def _read(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, dict) and value.get(name) is not None:
            return value[name]
        result = getattr(value, name, None)
        if result is not None:
            return result
    return None


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        result = value.model_dump(mode="json", exclude_none=True)
        return result if isinstance(result, dict) else {}
    return {}


def search_openai_web(*, api_key: str, model: str, query: str, timeout_seconds: float = 30.0) -> OpenAIWebSearchResponse:
    """Run required hosted web search and preserve its source list and citations."""
    try:
        from openai import OpenAI

        response = OpenAI(api_key=api_key, timeout=max(0.1, min(30.0, timeout_seconds))).responses.create(
            model=model,
            input=(
                "Search the web for sources relevant to this investigation query. Prioritize the "
                "requested source lane and jurisdiction. Return source discovery only; do not "
                "decide whether the claim is true. Query: "
                + query[:1200]
            ),
            tools=[{"type": "web_search", "search_context_size": "medium"}],
            tool_choice="required",
            include=["web_search_call.action.sources"],
        )
    except Exception as exc:
        raise OpenAIWebSearchError("OpenAI web search request failed") from exc

    candidates: list[dict[str, object]] = []
    citations: list[dict[str, object]] = []
    for output in getattr(response, "output", []) or []:
        output_type = _read(output, "type")
        if output_type == "web_search_call":
            action = _read(output, "action")
            action_data = _mapping(action)
            for source in action_data.get("sources", []) or []:
                item = _mapping(source)
                url = item.get("url")
                if isinstance(url, str):
                    candidates.append(
                        {
                            "url": url,
                            "title": item.get("title") or "",
                            "author": item.get("author") or "",
                            "publishedDate": item.get("published_date")
                            or item.get("publishedDate"),
                        }
                    )
        if output_type != "message":
            continue
        for content in _read(output, "content") or []:
            for annotation in _read(content, "annotations") or []:
                item = _mapping(annotation)
                if item.get("type") != "url_citation":
                    continue
                citation = _mapping(item.get("url_citation"))
                url = citation.get("url")
                if isinstance(url, str):
                    normalized = {
                        "url": url,
                        "title": citation.get("title") or "",
                    }
                    citations.append(normalized)
                    candidates.append(normalized)

    unique: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in candidates:
        url = item.get("url")
        if isinstance(url, str) and url not in seen:
            seen.add(url)
            unique.append(item)
    if not unique:
        raise OpenAIWebSearchError("OpenAI web search returned no source URLs")
    request_id = getattr(response, "id", None)
    return OpenAIWebSearchResponse(
        request_id=request_id if isinstance(request_id, str) else None,
        results=unique,
        citations=citations,
    )
