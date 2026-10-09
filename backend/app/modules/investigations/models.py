from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Boolean,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.domain.investigation import Channel, InputType, InvestigationStatus

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_subject: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    reference: Mapped[str] = mapped_column(String(20), unique=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="channel"))
    input_type: Mapped[InputType] = mapped_column(Enum(InputType, name="input_type"))
    status: Mapped[InvestigationStatus] = mapped_column(
        Enum(InvestigationStatus, name="investigation_status"), default=InvestigationStatus.RECEIVED
    )
    current_stage: Mapped[str] = mapped_column(String(40), default="RECEIVED")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="channel"), index=True)
    input_type: Mapped[InputType] = mapped_column(Enum(InputType, name="input_type"))
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source_metadata: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT, default=dict)


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("asset_role IN ('ORIGINAL', 'DERIVED')", name="asset_role_valid"),
        CheckConstraint(
            "parent_asset_id IS NULL OR parent_asset_id != id", name="asset_parent_not_self"
        ),
        CheckConstraint(
            "(asset_role = 'ORIGINAL' AND parent_asset_id IS NULL) OR "
            "(asset_role = 'DERIVED' AND parent_asset_id IS NOT NULL)",
            name="asset_parent_matches_role",
        ),
        UniqueConstraint(
            "parent_asset_id",
            "artifact_type",
            "transformation_version",
            name="uq_media_derivative_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    parent_asset_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    asset_role: Mapped[str] = mapped_column(
        String(20), default="ORIGINAL", server_default="ORIGINAL"
    )
    artifact_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    transformation_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    transformation_metadata: Mapped[dict[str, object] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    media_type: Mapped[str] = mapped_column(String(20))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(40), default="CHECKABLE_EVENT")
    needs_deep_investigation: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    source_role: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[str | None] = mapped_column(String(80), nullable=True)
    modified_at: Mapped[str | None] = mapped_column(String(80), nullable=True)
    discovery_method: Mapped[str] = mapped_column(String(40), default="MODEL_PROPOSED")
    discovery_trace_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("search_traces.id", ondelete="SET NULL"), nullable=True
    )
    retrieval_status: Mapped[str] = mapped_column(String(20), default="CANDIDATE")
    retrieval_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retrieval_failure_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceRelationship(Base):
    __tablename__ = "source_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "related_source_id", "relationship_type", name="uq_source_relationship"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    related_source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(30))
    basis: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvestigationUsage(Base):
    __tablename__ = "investigation_usage"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), unique=True
    )
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    search_calls: Mapped[int] = mapped_column(Integer, default=0)
    sources_discovered: Mapped[int] = mapped_column(Integer, default=0)
    sources_retrieved: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    limitations: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list)


class ModelUsageRecord(Base):
    __tablename__ = "model_usage_records"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(160))
    purpose: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="STARTED")
    failure_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SearchTrace(Base):
    __tablename__ = "search_traces"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(60), default="OPENAI_WEB_SEARCH")
    action: Mapped[str] = mapped_column(String(40), default="search")
    call_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_metadata: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT, default=dict)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provider-returned source list and citation annotations (not model-authored proposals).
    sources: Mapped[list[dict[str, object]]] = mapped_column(JSON_DOCUMENT, default=list)
    citations: Mapped[list[dict[str, object]]] = mapped_column(JSON_DOCUMENT, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "source_id IS NOT NULL OR media_asset_id IS NOT NULL",
            name="has_origin",
        ),
        UniqueConstraint("media_analysis_run_id", name="uq_evidence_media_analysis_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=True
    )
    media_asset_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=True
    )
    media_analysis_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("media_analysis_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(40))
    source_tier: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    stance: Mapped[str] = mapped_column(String(24), default="UNKNOWN")
    excerpt_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    independence_group_id: Mapped[str] = mapped_column(String(255), default="unknown")
    published_date: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_stale: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    retrieval_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    excerpt_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaAnalysisRun(Base):
    __tablename__ = "media_analysis_runs"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_media_analysis_run_cache_key"),
        CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="media_analysis_run_status_valid"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    media_asset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("media_assets.id", ondelete="CASCADE"), index=True
    )
    analyzer_id: Mapped[str] = mapped_column(String(40))
    analyzer_version: Mapped[str] = mapped_column(String(30))
    config_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    observations_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON_DOCUMENT, nullable=True
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_pair"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    relationship: Mapped[str] = mapped_column(String(30), default="UNKNOWN")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30))
    statement: Mapped[str] = mapped_column(Text)
    evidence_confidence: Mapped[str] = mapped_column(String(12), default="LOW")
    confidence_rationale: Mapped[str] = mapped_column(Text, default="")
    explanation_json: Mapped[list[dict[str, object]]] = mapped_column(JSON_DOCUMENT, default=list)
    unsupported_statements_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (
        UniqueConstraint("finding_id", "evidence_id", name="uq_finding_evidence_pair"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    finding_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )


class VerificationBrief(Base):
    __tablename__ = "verification_briefs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text)
    limitations: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (UniqueConstraint("idempotency_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(40), default="RECEIVED")
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    aggregate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    investigation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    event_metadata: Mapped[dict[str, object]] = mapped_column(JSON_DOCUMENT, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
