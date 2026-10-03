import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_MARKDOWN_LINK = re.compile(r"\]\((https?://[^\s)]+)", re.IGNORECASE)


def normalize_source_url(value: str) -> str:
    """Normalize obvious URL variants without changing meaningful query parameters."""
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if scheme not in {"http", "https"} or not hostname:
        raise ValueError("Source URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("Credential-bearing source URLs are not accepted")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Source URL has an invalid port") from exc
    netloc = hostname
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"
    path = parsed.path.rstrip("/")
    if path == "":
        path = "/"
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        folded = key.casefold()
        if (
            folded.startswith("utm_")
            or folded in TRACKING_PARAMETERS
            or folded
            in {
                "igshid",
                "mkt_tok",
                "mc_eid",
                "_hsenc",
                "_hsmi",
                "vero_id",
            }
        ):
            continue
        query.append((key, item))
    query.sort()
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def extract_markdown_link_urls(value: str) -> set[str]:
    """Extract explicit public HTTP(S) links from reader-produced Markdown."""
    urls: set[str] = set()
    for match in _MARKDOWN_LINK.findall(value):
        try:
            urls.add(normalize_source_url(match.rstrip(".,;")))
        except ValueError:
            continue
    return urls
