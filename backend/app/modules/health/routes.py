import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.storage.s3 import check_bucket

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


def _check_dependency(name: str, check: Callable[[], object]) -> None:
    try:
        check()
    except Exception as error:
        # Expose only the dependency name. SDK exception strings can contain
        # hostnames or request details and should not be returned to callers.
        logger.warning("Readiness dependency check failed dependency=%s", name)
        raise HTTPException(
            status_code=503,
            detail={"code": "REQUIRED_DEPENDENCY_UNAVAILABLE", "dependency": name},
        ) from error


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def readiness() -> dict[str, str]:
    settings = get_settings()
    openai_configured = bool(
        settings.openai_api_key and settings.openai_api_key.get_secret_value().strip()
    )
    search_ready = bool(settings.exa_api_key and settings.exa_api_key.get_secret_value().strip())
    redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=1)
    try:
        def check_database() -> None:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

        _check_dependency("database", check_database)
        _check_dependency("redis", redis_client.ping)
        _check_dependency("object_storage", check_bucket)
    finally:
        redis_client.close()
    return {
        "status": "ready",
        "database": "ok",
        "redis": "ok",
        "object_storage": "ok",
        "investigation_engine": "configured" if openai_configured else "missing_openai_api_key",
        "model_provider": "openai",
        "web_search": "configured" if search_ready else "missing_exa_api_key",
    }
