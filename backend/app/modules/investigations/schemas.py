from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.domain.investigation import InputType, InvestigationStatus
from app.modules.investigations.triage import ClaimType


class CreateInvestigationRequest(BaseModel):
    input_type: InputType = InputType.TEXT
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("content must not be blank")
        return content

    @field_validator("input_type")
    @classmethod
    def validate_supported_type(cls, value: InputType) -> InputType:
        if value not in {InputType.TEXT, InputType.URL}:
            raise ValueError("use the media upload endpoint for IMAGE or VIDEO submissions")
        return value

    @field_validator("content")
    @classmethod
    def validate_url_content(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("input_type") == InputType.URL:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("URL submissions must use an absolute http(s) URL")
            if parsed.username or parsed.password:
                raise ValueError("URLs containing embedded credentials are not accepted")
        return value


class TriageRequest(BaseModel):
    input_type: InputType = InputType.TEXT
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Add a claim or question before reviewing the triage.")
        return content

    @field_validator("input_type")
    @classmethod
    def validate_supported_type(cls, value: InputType) -> InputType:
        if value not in {InputType.TEXT, InputType.URL}:
            raise ValueError("Triage accepts a claim or public URL. Add media after claim review.")
        return value


class TriageClaimInput(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    claim_type: ClaimType
    needs_deep_investigation: bool

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def enforce_investigation_depth(self) -> "TriageClaimInput":
        self.needs_deep_investigation = self.claim_type != "SETTLED_FACT"
        return self


class ContinueInvestigationRequest(BaseModel):
    claims: list[TriageClaimInput] = Field(min_length=1, max_length=3)

    @field_validator("claims")
    @classmethod
    def require_distinct_atomic_claims(cls, claims: list[TriageClaimInput]) -> list[TriageClaimInput]:
        normalized = [" ".join(item.text.casefold().split()) for item in claims]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Each claim must be distinct. Remove or combine duplicate claims.")
        return claims

class InvestigationResponse(BaseModel):
    id: UUID
    reference: str
    status: InvestigationStatus
    input_type: InputType
    current_stage: str
    created_at: datetime
    failure_reason: str | None = None

    model_config = {"from_attributes": True}


class InvestigationHistoryResponse(BaseModel):
    id: UUID
    reference: str
    status: InvestigationStatus
    input_type: InputType
    current_stage: str
    created_at: datetime
    title: str
    finding_status: str | None = None
    sources_count: int = 0
