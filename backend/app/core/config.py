from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    auth_mode: Literal["disabled", "oidc"] = "disabled"
    database_url: str = "postgresql+psycopg://agent_zero:agent_zero_local@localhost:5433/agent_zero"
    redis_url: str = "redis://localhost:6379/0"
    object_storage_endpoint: str = "http://localhost:9000"
    object_storage_bucket: str = "agent-zero"
    object_storage_access_key: str = "agentzero"
    object_storage_secret_key: str = "local-development-only"
    object_storage_region: str = "us-east-1"
    object_storage_secure: bool = False
    log_level: str = "INFO"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6-luna"
    openai_reasoning_effort: Literal["low", "medium"] = "low"
    exa_api_key: SecretStr | None = None
    max_media_bytes: int = 25_000_000
    max_image_pixels: int = 20_000_000
    source_reader_provider: Literal["disabled", "jina_reader"] = "disabled"
    max_model_calls_per_investigation: int = 4
    max_claims_per_investigation: int = 3
    max_search_queries: int = 5
    max_search_results_per_query: int = 5
    max_sources_per_investigation: int = 8
    max_retrieved_sources: int = 5
    # Acquisition is bounded separately from the evidence/model context budgets.
    max_retrieved_document_chars: int = 60_000
    max_matching_regions_per_claim: int = 4
    max_source_chars_per_source: int = 6_000
    max_total_evidence_chars: int = 24_000
    max_evidence_windows_per_source_per_claim: int = 2
    max_images_to_model: int = 4
    max_model_output_tokens_research: int = 700
    max_model_output_tokens_synthesis: int = 900
    max_provider_retries: int = 1
    max_retry_after_seconds: float = 5.0
    model_request_timeout_seconds: float = 45.0
    max_model_input_chars: int = 12_000
    clickcast_api_token: SecretStr | None = None
    clickcast_identity_key: SecretStr | None = None
    clickcast_owner_id: UUID | None = None

    @model_validator(mode="after")
    def require_auth_outside_development(self) -> "Settings":
        if self.app_env in {"staging", "production"} and self.auth_mode == "disabled":
            raise ValueError("AUTH_MODE=oidc is required outside local development/test")
        if self.app_env in {"staging", "production"} and not self.object_storage_secure:
            raise ValueError(
                "OBJECT_STORAGE_SECURE=true is required outside local development/test"
            )
        if self.app_env in {"staging", "production"}:
            raise ValueError(
                "Production deployment is blocked until the authentication adapter is implemented"
            )
        if self.clickcast_api_token:
            api_token = self.clickcast_api_token.get_secret_value()
            identity_key = (
                self.clickcast_identity_key.get_secret_value()
                if self.clickcast_identity_key
                else ""
            )
            if len(api_token) < 32 or not api_token.isalnum():
                raise ValueError(
                    "CLICKCAST_API_TOKEN must be at least 32 alphanumeric characters"
                )
            if len(identity_key) < 32:
                raise ValueError(
                    "CLICKCAST_IDENTITY_KEY must be at least 32 characters when intake is enabled"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
