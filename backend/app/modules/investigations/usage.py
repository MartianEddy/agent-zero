from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.conversations.models import WhatsAppConversation
from app.modules.investigations.models import (
    AuditEvent,
    InvestigationUsage,
    ModelUsageRecord,
)


class ModelCallBudgetExceeded(RuntimeError):
    pass


def get_or_create_usage(session: Session, investigation_id: UUID) -> InvestigationUsage:
    usage = session.scalar(
        select(InvestigationUsage).where(InvestigationUsage.investigation_id == investigation_id)
    )
    if usage is None:
        usage = InvestigationUsage(investigation_id=investigation_id)
        session.add(usage)
        session.flush()
    return usage


def add_limitation(session: Session, investigation_id: UUID, message: str) -> None:
    usage = get_or_create_usage(session, investigation_id)
    if message in usage.limitations:
        return
    usage.limitations = [*usage.limitations, message]
    session.add(
        AuditEvent(
            investigation_id=investigation_id,
            event_type="INVESTIGATION_LIMITATION_RECORDED",
            actor="system",
            event_metadata={"limitation": message},
        )
    )
    session.commit()


class ModelCallBudget:
    def __init__(
        self,
        session: Session,
        investigation_id: UUID | None = None,
        conversation_id: UUID | None = None,
    ) -> None:
        if (investigation_id is None) == (conversation_id is None):
            raise ValueError("Exactly one model usage owner is required")
        self.session = session
        self.investigation_id = investigation_id
        self.conversation_id = conversation_id
        self.limit = (
            get_settings().max_model_calls_per_investigation
            if investigation_id is not None
            else get_settings().max_model_calls_per_whatsapp_conversation
        )

    def begin(
        self, *, provider: str, model: str, purpose: str, commit: bool = True
    ) -> ModelUsageRecord:
        usage = (
            get_or_create_usage(self.session, self.investigation_id)
            if self.investigation_id is not None
            else None
        )
        conversation = (
            self.session.get(WhatsAppConversation, self.conversation_id, with_for_update=True)
            if self.conversation_id is not None
            else None
        )
        if usage is None and conversation is None:
            raise ValueError("Model usage owner was not found")
        model_calls = usage.model_calls if usage is not None else conversation.model_calls
        if model_calls >= self.limit:
            message = (
                "Investigation model-call budget reached."
                if usage is not None
                else "WhatsApp conversation model-call budget reached."
            )
            if usage is not None and message not in usage.limitations:
                usage.limitations = [*usage.limitations, message]
                self.session.add(
                    AuditEvent(
                        investigation_id=self.investigation_id,
                        event_type="MODEL_BUDGET_REACHED",
                        actor="system",
                        event_metadata={"limit": self.limit, "model_calls": usage.model_calls},
                    )
                )
                if commit:
                    self.session.commit()
            raise ModelCallBudgetExceeded(message)
        if usage is not None:
            usage.model_calls += 1
        elif conversation is not None:
            conversation.model_calls += 1
        record = ModelUsageRecord(
            investigation_id=self.investigation_id,
            conversation_id=self.conversation_id,
            provider=provider,
            model=model,
            purpose=purpose,
            status="STARTED",
        )
        self.session.add(record)
        if commit:
            self.session.commit()
            self.session.refresh(record)
        else:
            self.session.flush()
        return record


def _read(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, dict) and value.get(name) is not None:
            return value[name]
        item = getattr(value, name, None)
        if item is not None:
            return item
    return None


def token_usage(raw_responses: list[Any]) -> tuple[int | None, int | None, int | None, int | None]:
    input_total = output_total = cached_total = total_total = 0
    saw_input = saw_output = saw_cached = saw_total = False
    for raw in raw_responses:
        response = _read(raw, "response") or raw
        usage = _read(response, "usage")
        if usage is None:
            continue
        input_value = _read(usage, "input_tokens", "prompt_tokens")
        output_value = _read(usage, "output_tokens", "completion_tokens")
        total_value = _read(usage, "total_tokens")
        details = _read(usage, "input_tokens_details", "prompt_tokens_details")
        cached_value = _read(details, "cached_tokens") if details is not None else None
        if input_value is not None:
            input_total += int(input_value)
            saw_input = True
        if output_value is not None:
            output_total += int(output_value)
            saw_output = True
        if cached_value is not None:
            cached_total += int(cached_value)
            saw_cached = True
        if total_value is not None:
            total_total += int(total_value)
            saw_total = True
    input_tokens = input_total if saw_input else None
    output_tokens = output_total if saw_output else None
    total_tokens = (
        total_total
        if saw_total
        else (input_total + output_total if saw_input and saw_output else None)
    )
    return input_tokens, cached_total if saw_cached else None, output_tokens, total_tokens


def complete_model_call(
    session: Session,
    record: ModelUsageRecord,
    raw_responses: list[Any],
    *,
    commit: bool = True,
) -> None:
    input_tokens, cached_tokens, output_tokens, total_tokens = token_usage(raw_responses)
    record.status = "COMPLETED"
    record.input_tokens = input_tokens
    record.cached_input_tokens = cached_tokens
    record.output_tokens = output_tokens
    record.total_tokens = total_tokens
    if record.investigation_id is not None:
        usage = get_or_create_usage(session, record.investigation_id)
        if input_tokens is not None:
            usage.input_tokens += input_tokens
        if cached_tokens is not None:
            usage.cached_input_tokens += cached_tokens
        if output_tokens is not None:
            usage.output_tokens += output_tokens
        session.add(
            AuditEvent(
                investigation_id=record.investigation_id,
                event_type="MODEL_CALL_COMPLETED",
                actor="system",
                event_metadata={
                    "provider": record.provider,
                    "model": record.model,
                    "purpose": record.purpose,
                },
            )
        )
    elif record.conversation_id is not None:
        conversation = session.get(WhatsAppConversation, record.conversation_id)
        if conversation is not None:
            conversation.input_tokens += input_tokens or 0
            conversation.output_tokens += output_tokens or 0
    if commit:
        session.commit()


def fail_model_call(
    session: Session,
    record: ModelUsageRecord,
    category: str,
    *,
    http_status: int | None = None,
    request_id: str | None = None,
    retryable: bool | None = None,
    raw_responses: list[Any] | None = None,
    commit: bool = True,
) -> None:
    record.status = "FAILED"
    record.failure_category = category
    if raw_responses:
        input_tokens, cached_tokens, output_tokens, total_tokens = token_usage(raw_responses)
        record.input_tokens = input_tokens
        record.cached_input_tokens = cached_tokens
        record.output_tokens = output_tokens
        record.total_tokens = total_tokens
        if record.investigation_id is not None:
            usage = get_or_create_usage(session, record.investigation_id)
            if input_tokens is not None:
                usage.input_tokens += input_tokens
            if cached_tokens is not None:
                usage.cached_input_tokens += cached_tokens
            if output_tokens is not None:
                usage.output_tokens += output_tokens
        elif record.conversation_id is not None:
            conversation = session.get(WhatsAppConversation, record.conversation_id)
            if conversation is not None:
                conversation.input_tokens += input_tokens or 0
                conversation.output_tokens += output_tokens or 0
    metadata: dict[str, object] = {
        "provider": record.provider,
        "model": record.model,
        "purpose": record.purpose,
        "failure_category": category,
    }
    if http_status is not None:
        metadata["http_status"] = http_status
    if request_id:
        metadata["request_id"] = request_id[:160]
    if retryable is not None:
        metadata["retryable"] = retryable
    if record.investigation_id is not None:
        session.add(
            AuditEvent(
                investigation_id=record.investigation_id,
                event_type="MODEL_CALL_FAILED",
                actor="system",
                event_metadata=metadata,
            )
        )
    if commit:
        session.commit()
