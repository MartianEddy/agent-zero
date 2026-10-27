from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.responses import Response

from app.core.logging import configure_logging
from app.core.request_context import request_id_var
from app.core.tracing import configure_tracing, flush_tracing, tracer
from app.modules.channels.clickcast import router as clickcast_router
from app.modules.channels.whatsapp import router as whatsapp_router
from app.modules.health.routes import router as health_router
from app.modules.investigations.routes import router as investigations_router

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from app.core.config import get_settings

    configure_tracing(get_settings().otel_exporter_otlp_endpoint)
    try:
        yield
    finally:
        flush_tracing()


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
        with tracer(__name__).start_as_current_span(
            "http.server", record_exception=False, set_status_on_exception=False
        ) as span:
            span.set_attribute("http.request.method", request.method)
            span.set_attribute("agent_zero.request_id", request_id)
            try:
                response = await call_next(request)
            except Exception:
                span.set_attribute("http.response.status_code", 500)
                span.set_attribute("error", True)
                raise
            route = request.scope.get("route")
            if route is not None and getattr(route, "path", None):
                span.set_attribute("http.route", route.path)
            span.set_attribute("http.response.status_code", response.status_code)
            span.set_attribute("error", response.status_code >= 500)
            response.headers["X-Request-ID"] = request_id
            return response
    finally:
        request_id_var.reset(token)


app.include_router(health_router, prefix="/api/v1")
app.include_router(investigations_router, prefix="/api/v1")
app.include_router(clickcast_router, prefix="/api/v1")
app.include_router(whatsapp_router, prefix="/api/v1")
