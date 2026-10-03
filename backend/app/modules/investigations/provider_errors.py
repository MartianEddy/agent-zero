from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any


class FailureCategory(StrEnum):
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    DERIVATION_FAILED = "DERIVATION_FAILED"
    STORAGE_FAILED = "STORAGE_FAILED"


def _provider_message(error: Exception) -> str:
    response = getattr(error, "response", None)
    try:
        payload: Any = response.json() if response is not None else None
    except Exception:
        payload = None
    message = getattr(error, "message", None) or str(error)
    if isinstance(payload, dict):
        nested = payload.get("error")
        if isinstance(nested, dict):
            message = " ".join((str(message), str(nested.get("message", ""))))
        else:
            message = " ".join((str(message), str(payload)))
    return str(message).casefold()


def classify_provider_error(error: Exception) -> FailureCategory:
    """Map provider/SDK exceptions to stable operational categories."""
    status = getattr(error, "status_code", None)
    name = type(error).__name__.casefold()
    module = type(error).__module__.casefold()
    message = _provider_message(error)
    if status in {401, 403} or "authentication" in name or "permissiondenied" in name:
        return FailureCategory.AUTHENTICATION_FAILED
    if status == 429 or "ratelimit" in name:
        if any(
            term in message for term in ("quota", "billing", "insufficient_quota", "daily limit")
        ):
            return FailureCategory.QUOTA_EXHAUSTED
        return FailureCategory.RATE_LIMITED
    if "timeout" in name:
        return FailureCategory.TIMEOUT
    if status in {408, 500, 502, 503, 504} or "connectionerror" in name:
        return FailureCategory.PROVIDER_UNAVAILABLE
    if "modelbehavior" in name or "outputparse" in name or "validationerror" in name:
        return FailureCategory.INVALID_MODEL_OUTPUT
    if module.startswith(("openai", "agents")):
        return FailureCategory.PROVIDER_UNAVAILABLE
    return FailureCategory.PIPELINE_ERROR


def retry_after_seconds(error: Exception) -> float | None:
    """Read Retry-After as seconds; callers decide whether the delay is acceptable."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def is_retryable(category: FailureCategory) -> bool:
    return category in {
        FailureCategory.RATE_LIMITED,
        FailureCategory.PROVIDER_UNAVAILABLE,
        FailureCategory.TIMEOUT,
    }
