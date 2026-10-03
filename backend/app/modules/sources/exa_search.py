"""Small HTTP adapter for Exa's native search endpoint."""

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ExaSearchError(RuntimeError):
    """Raised when Exa cannot return a usable search response."""


@dataclass(frozen=True)
class ExaSearchResponse:
    request_id: str | None
    results: list[dict[str, object]]


def search_exa(*, api_key: str, query: str, num_results: int = 5) -> ExaSearchResponse:
    """Search Exa and return provider results with token-efficient highlights."""
    body = json.dumps(
        {
            "query": query,
            "type": "auto",
            "numResults": max(1, min(num_results, 10)),
            "contents": {"highlights": True},
        }
    ).encode("utf-8")
    request = Request(
        "https://api.exa.ai/search",
        data=body,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ExaSearchError("Exa search request failed") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ExaSearchError("Exa returned an unexpected search response")

    results: list[dict[str, object]] = []
    for item in payload["results"]:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        results.append(
            {
                key: item[key]
                for key in ("title", "url", "author", "publishedDate", "highlights")
                if key in item
            }
        )
    return ExaSearchResponse(
        request_id=payload.get("requestId") if isinstance(payload.get("requestId"), str) else None,
        results=results,
    )
