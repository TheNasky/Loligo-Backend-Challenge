"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.suggestions import router as suggestions_router
from app.config import get_settings, validate_runtime_settings
from app.services.telemetry import get_telemetry

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks (like NestJS onModuleInit / onModuleDestroy)."""
    logging.basicConfig(level=settings.log_level)
    validate_runtime_settings(settings)
    logging.getLogger(__name__).info("Inkflow API starting")
    yield
    logging.getLogger(__name__).info("Inkflow API shutting down")


app = FastAPI(
    title="Inkflow API",
    description="Conversational investment analysis agent with per-conversation memory.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(suggestions_router)


@app.get("/health")
def health() -> dict:
    """Liveness probe for Docker and load balancers."""
    return {
        "status": "ok",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/metrics")
def metrics() -> dict:
    """Operational counters for basic runtime monitoring."""
    return get_telemetry().snapshot()
