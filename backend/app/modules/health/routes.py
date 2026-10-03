from fastapi import APIRouter, HTTPException
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.storage.s3 import check_bucket

router = APIRouter(tags=["health"])


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
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        redis_client.ping()
        check_bucket()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Required dependency is unavailable") from error
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
