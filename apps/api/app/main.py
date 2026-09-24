import logging
from hmac import compare_digest
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine
from app.core.metrics import RuntimeMetrics
from app.modules.admin.router import router as admin_router
from app.modules.assistant.router import router as assistant_router
from app.modules.auth.router import router as auth_router
from app.modules.conversations.router import router as conversations_router
from app.modules.family_spaces.router import router as family_spaces_router
from app.modules.memory.router import router as memory_router
from app.modules.neural.router import router as neural_router
from app.modules.personal.router import router as personal_router
from app.modules.realtime.router import router as realtime_router
from app.modules.secret.router import router as secret_router

settings = get_settings()
http_logger = logging.getLogger("cocoon.http")
runtime_metrics = RuntimeMetrics()
app = FastAPI(
    title="Cocoon API",
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

# Native builds do not require CORS. Browser previews must declare their exact origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=bool(settings.cors_origins),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Last-Event-ID",
        "X-Assistant-Idempotency-Key",
        "X-Capture-Idempotency-Key",
        "X-Cocoon-Secret-Access",
        "X-Metrics-Token",
        "X-Proposal-Version",
        "X-Request-ID",
    ],
)


@app.middleware("http")
async def prevent_api_caching(request: Request, call_next):
    raw_request_id = request.headers.get("X-Request-ID")
    try:
        request_id = str(UUID(raw_request_id)) if raw_request_id else str(uuid4())
    except (ValueError, AttributeError):
        request_id = str(uuid4())
    started = perf_counter()
    runtime_metrics.begin_request()
    try:
        response = await call_next(request)
    except Exception:
        runtime_metrics.observe_request(
            request.method, 500, perf_counter() - started
        )
        http_logger.exception(
            "request_failed method=%s path=%s status=500 duration_ms=%d request_id=%s",
            request.method,
            request.url.path,
            round((perf_counter() - started) * 1000),
            request_id,
        )
        raise
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id
    runtime_metrics.observe_request(request.method, response.status_code, perf_counter() - started)
    http_logger.info(
        "request_complete method=%s path=%s status=%s duration_ms=%d request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        round((perf_counter() - started) * 1000),
        request_id,
    )
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness() -> dict[str, str]:
    """Readiness probe: migrations have run and the primary database responds."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on deployment infrastructure
        raise HTTPException(status_code=503, detail="database_not_ready") from exc
    return {"status": "ready"}


@app.get("/internal/metrics", include_in_schema=False)
def metrics(request: Request) -> PlainTextResponse:
    """Expose metrics only to an explicitly authenticated private scraper."""
    configured_token = settings.metrics_token
    supplied_token = request.headers.get("X-Metrics-Token")
    if (
        not configured_token
        or not supplied_token
        or not compare_digest(supplied_token, configured_token)
    ):
        raise HTTPException(status_code=404, detail="Not found")
    return PlainTextResponse(
        runtime_metrics.render_prometheus(), media_type="text/plain; version=0.0.4"
    )


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(assistant_router)
app.include_router(personal_router)
app.include_router(neural_router)
app.include_router(memory_router)
app.include_router(conversations_router)
app.include_router(secret_router)
app.include_router(family_spaces_router)
app.include_router(realtime_router)
