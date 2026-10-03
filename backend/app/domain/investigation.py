from enum import StrEnum


class InvestigationStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    ANALYZING = "ANALYZING"
    RESEARCHING = "RESEARCHING"
    CORROBORATING = "CORROBORATING"
    GENERATING_BRIEF = "GENERATING_BRIEF"
    COMPLETE = "COMPLETE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Channel(StrEnum):
    WEB = "WEB"
    WHATSAPP = "WHATSAPP"
    API = "API"


class InputType(StrEnum):
    TEXT = "TEXT"
    URL = "URL"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"


ALLOWED_TRANSITIONS: dict[InvestigationStatus, frozenset[InvestigationStatus]] = {
    InvestigationStatus.RECEIVED: frozenset(
        {InvestigationStatus.PROCESSING, InvestigationStatus.CANCELLED, InvestigationStatus.FAILED}
    ),
    InvestigationStatus.PROCESSING: frozenset(
        {
            InvestigationStatus.ANALYZING,
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
        }
    ),
    InvestigationStatus.ANALYZING: frozenset(
        {
            InvestigationStatus.RESEARCHING,
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
        }
    ),
    InvestigationStatus.RESEARCHING: frozenset(
        {
            InvestigationStatus.CORROBORATING,
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
        }
    ),
    InvestigationStatus.CORROBORATING: frozenset(
        {
            InvestigationStatus.GENERATING_BRIEF,
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
        }
    ),
    InvestigationStatus.GENERATING_BRIEF: frozenset(
        {
            InvestigationStatus.COMPLETE,
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
        }
    ),
    InvestigationStatus.NEEDS_REVIEW: frozenset(
        {InvestigationStatus.PROCESSING, InvestigationStatus.CANCELLED}
    ),
    InvestigationStatus.COMPLETE: frozenset(),
    InvestigationStatus.FAILED: frozenset({InvestigationStatus.PROCESSING}),
    InvestigationStatus.CANCELLED: frozenset(),
}


def validate_transition(current: InvestigationStatus, target: InvestigationStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Invalid investigation transition: {current} -> {target}")
