from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.domain.investigation import InputType, InvestigationStatus


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


class InvestigationResponse(BaseModel):
    id: UUID
    reference: str
    status: InvestigationStatus
    current_stage: str
    created_at: datetime
    failure_reason: str | None = None

    model_config = {"from_attributes": True}
