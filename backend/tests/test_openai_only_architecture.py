from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from app.core.config import Settings
from app.modules.health.routes import readiness


def test_settings_define_openai_without_alternative_provider_routing() -> None:
    fields = Settings.model_fields
    assert "openai_api_key" in fields
    assert "openai_model" in fields
    assert "gemini_api_key" not in fields
    assert "groq_api_key" not in fields
    assert "openrouter_api_key" not in fields
    assert "ai_fallback_provider" not in fields
    assert "ai_last_resort_provider" not in fields


def test_readiness_checks_configuration_without_calling_a_model() -> None:
    settings = Settings(
        openai_api_key=SecretStr("mock-key"),
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
    )
    connection = MagicMock()
    connection.__enter__.return_value = connection
    redis_client = MagicMock()
    redis_client.ping.return_value = True
    with (
        patch("app.modules.health.routes.get_settings", return_value=settings),
        patch("app.modules.health.routes.engine.connect", return_value=connection),
        patch("app.modules.health.routes.Redis.from_url", return_value=redis_client),
        patch("app.modules.health.routes.check_bucket"),
    ):
        result = readiness()

    assert result["model_provider"] == "openai"
    assert result["investigation_engine"] == "configured"
    assert "configured_model_providers" not in result
