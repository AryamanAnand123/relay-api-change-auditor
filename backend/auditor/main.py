"""Section 7: portfolio-ready local compatibility workspace."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from auditor import __version__
from auditor.config import Settings
from auditor.uploads import UploadBoundary, router as specification_router
from auditor.history import HistoryStore, HistoryUnavailable, HistoryFull, RunNotFound, InvalidCursor
from auditor.history_api import HistoryOriginBoundary, router as history_router
from auditor.exports import ExportTooLarge
from auditor.frontend import frontend_router
from auditor.explanations import ExplanationService
from auditor.explanation_api import router as explanation_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            app.state.history.close()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Relay: evaluated API compatibility workspace with evidence, history, exports, and optional LangChain guidance.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.history = HistoryStore(settings)
    app.state.explanations = ExplanationService(settings)
    app.include_router(specification_router)
    app.include_router(history_router)
    app.include_router(explanation_router)
    app.include_router(frontend_router(settings.frontend_dist))
    app.add_middleware(UploadBoundary)
    app.add_middleware(HistoryOriginBoundary)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    for error_type, status, code in (
        (HistoryUnavailable, 503, "history_unavailable"), (HistoryFull, 409, "history_full"),
        (RunNotFound, 404, "comparison_not_found"), (InvalidCursor, 400, "invalid_cursor"),
        (ExportTooLarge, 413, "export_too_large"),
    ):
        async def handle_error(request, error, response_status=status, response_code=code):
            return JSONResponse({"detail": {"code": response_code, "message": str(error)}}, status_code=response_status)
        app.add_exception_handler(error_type, handle_error)

    @app.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/system", tags=["System"])
    async def index():
        return {
            "name": settings.app_name,
            "stage": "portfolio_ready",
            "health_url": "/health",
            "schema_url": "/openapi.json",
            "validation_url": "/api/specifications/validate",
            "comparison_url": "/api/specifications/compare",
            "history_url": "/api/comparisons",
            "database_url": "/api/system/database",
            "ai_status_url": "/api/ai/status",
            "message": "Relay browser workspace is available at /. Optional LangChain explanations use the configured Groq Free-plan key.",
        }

    @app.get("/health", tags=["System"])
    async def health():
        return {"status": "ok", "section": 7, "version": __version__}

    return app


app = create_app()
