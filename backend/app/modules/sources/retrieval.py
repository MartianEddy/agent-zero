"""Bounded public-page retrieval through Agent Reach's documented Jina Reader path.

Agent Reach is an installer/router for local agent capabilities, not an API that a
FastAPI worker can call. This adapter talks to its selected public web-reading
backend directly and keeps that provider replaceable.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_PAGE_BYTES = 300_000
MAX_PAGE_CHARS = 60_000
READ_TIMEOUT_SECONDS = 15
READER_HOST = "r.jina.ai"


class SourceRetrievalError(ValueError):
    """A source could not be safely retrieved or parsed."""


@dataclass(frozen=True)
class RetrievedPage:
    requested_url: str
    text: str
    provider: str = "jina_reader"
    title: str | None = None
    canonical_url: str | None = None
    author: str | None = None
    published_at: str | None = None
    modified_at: str | None = None


def parse_reader_response(value: str) -> RetrievedPage:
    """Separate Jina Reader's small metadata preamble from the page body."""
    metadata: dict[str, str] = {}
    lines = value.splitlines()
    body_start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().casefold() == "markdown content:"
        ),
        None,
    )
    if body_start is None:
        body = value.strip()
    else:
        for line in lines[:body_start]:
            key, separator, content = line.partition(":")
            if separator:
                metadata[key.strip().casefold()] = content.strip()
        body = "\n".join(lines[body_start + 1 :]).strip()

    def value_for(*keys: str) -> str | None:
        return next((metadata[key] for key in keys if metadata.get(key)), None)

    canonical = value_for("url source", "canonical url")
    if canonical:
        try:
            parsed = urlsplit(canonical)
        except ValueError:
            canonical = None
        else:
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                canonical = None
    return RetrievedPage(
        requested_url="",
        text=body,
        title=value_for("title"),
        canonical_url=canonical,
        author=value_for("author", "byline"),
        published_at=value_for("published time", "published", "date published"),
        modified_at=value_for("last modified", "modified time", "date modified"),
    )


def validate_public_http_url(url: str) -> str:
    """Reject malformed URLs and destinations that should never be fetched."""
    if len(url) > 4_000:
        raise SourceRetrievalError("Source URL exceeds the configured limit")
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise SourceRetrievalError("Source URL is malformed") from exc
    try:
        port = parsed.port
    except ValueError as exc:
        raise SourceRetrievalError("URL contains an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in {None, 80, 443}
    ):
        raise SourceRetrievalError("URL is not an allowed public HTTP(S) address")
    sensitive_query_keys = {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "credential",
        "key",
        "password",
        "secret",
        "session",
        "sig",
        "signature",
        "token",
    }
    if any(key.casefold() in sensitive_query_keys for key, _ in parse_qsl(parsed.query)):
        raise SourceRetrievalError(
            "URLs with credential-like query parameters are not sent upstream"
        )

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost"):
        raise SourceRetrievalError("Local destinations are not retrievable")

    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            answers = socket.getaddrinfo(
                hostname, port or (443 if parsed.scheme == "https" else 80)
            )
        except OSError as exc:
            raise SourceRetrievalError("Source hostname could not be resolved") from exc
        addresses = {ipaddress.ip_address(answer[4][0]) for answer in answers}

    if not addresses or any(not address.is_global for address in addresses):
        raise SourceRetrievalError("Private or non-public source destinations are blocked")
    return parsed._replace(fragment="").geturl()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def read_public_page(url: str) -> RetrievedPage:
    """Read a public page using Jina Reader, returning bounded plain text only.

    The target URL is sent to the configured upstream reader. No user media,
    cookies, or account credentials are sent. Retrieval is opt-in at application
    configuration level; the caller should only invoke this when enabled.
    """
    target = validate_public_http_url(url)
    reader_url = f"https://{READER_HOST}/" + quote(target, safe=":/")
    request = Request(
        reader_url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "AgentZero/0.1 source-reader",
            "X-Return-Format": "text",
        },
    )
    try:
        opener = build_opener(_NoRedirect)
        with opener.open(request, timeout=READ_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise SourceRetrievalError(f"Source reader returned HTTP {response.status}")
            content_type = response.headers.get_content_type()
            if content_type not in {"text/plain", "text/markdown", "text/html"}:
                raise SourceRetrievalError("Source reader returned an unsupported content type")
            payload = response.read(MAX_PAGE_BYTES + 1)
    except HTTPError as exc:
        raise SourceRetrievalError(f"Source reader returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceRetrievalError("Source reader request failed") from exc

    if len(payload) > MAX_PAGE_BYTES:
        raise SourceRetrievalError("Retrieved page exceeds the configured size limit")
    raw_text = payload.decode("utf-8", errors="replace").strip()
    if not raw_text:
        raise SourceRetrievalError("Source reader returned an empty page")
    page = parse_reader_response(raw_text)
    if not page.text:
        raise SourceRetrievalError("Source reader returned an empty page")
    return RetrievedPage(
        requested_url=target,
        text=page.text[:MAX_PAGE_CHARS],
        provider="jina_reader",
        title=page.title,
        canonical_url=page.canonical_url,
        author=page.author,
        published_at=page.published_at,
        modified_at=page.modified_at,
    )


def excerpt_is_present(excerpt: str, page_text: str) -> bool:
    """Check that a proposed quotation exists in the fetched source text."""

    def normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    quote_text = normalize(excerpt.strip(" \t\n\r\"'“”‘’…"))
    source_text = normalize(page_text)
    return len(quote_text) >= 24 and quote_text in source_text
