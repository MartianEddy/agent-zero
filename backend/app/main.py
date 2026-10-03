from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.responses import Response

from app.core.logging import configure_logging
from app.core.request_context import request_id_var
from app.modules.health.routes import router as health_router
from app.modules.channels.clickcast import router as clickcast_router
from app.modules.investigations.routes import router as investigations_router

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(
    title="Agent 0 Investigation API",
    version="0.1.0",
    description="Channel-neutral API for evidence-backed investigations.",
    lifespan=lifespan,
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next) -> Response:
    request_id = uuid4().hex
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(token)


app.include_router(health_router, prefix="/api/v1")
app.include_router(investigations_router, prefix="/api/v1")
app.include_router(clickcast_router, prefix="/api/v1")
