"""Privacy-safe, opt-in OpenTelemetry tracing for Agent Zero lifecycle spans."""

from __future__ import annotations

import logging
from functools import lru_cache

from opentelemetry import trace

logger = logging.getLogger(__name__)
SERVICE_NAME = "agent-zero"


@lru_cache(maxsize=1)
def configure_tracing(endpoint: str | None) -> None:
    """Enable OTLP only when configured; never collect request or evidence bodies."""
    if not endpoint:
        return
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
    except Exception:
        # Instrumentation must not prevent API or worker startup.
        logger.warning("OpenTelemetry could not be configured; tracing remains disabled")


def tracer(name: str):
    return trace.get_tracer(name)


def flush_tracing() -> None:
    provider = trace.get_tracer_provider()
    shutdown = getattr(provider, "shutdown", None)
    if shutdown:
        shutdown()
