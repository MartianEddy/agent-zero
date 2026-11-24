"""Redaction for any text that may be kept for evaluation or training."""

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# International (+254 ...) and Kenyan local (07xx / 01xx) numbers, with common separators.
_PHONE = re.compile(
    r"(?<![\w])(?:\+?\d{1,3}[\s-]?)?(?:\(?0?\d{2,3}\)?[\s-]?)\d{3}[\s-]?\d{3,4}(?!\w)"
)
_LONG_NUMBER = re.compile(r"\b\d{9,}\b")
_ID_LIKE = re.compile(r"\b[A-Z]{2,3}[- ]?\d{6,}\b")


def redact_pii(text: str) -> str:
    """Replace emails, phone numbers, and long identifier-like numbers with placeholders."""
    value = _EMAIL.sub("[email]", text or "")
    value = _LONG_NUMBER.sub("[number]", value)
    value = _PHONE.sub("[phone]", value)
    return _ID_LIKE.sub("[id]", value)
