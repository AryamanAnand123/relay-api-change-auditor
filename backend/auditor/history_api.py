"""Single-user local history; private shared deployment requires authentication."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from auditor.exports import json_export, markdown_export
from auditor.uploads import upload_pair

router = APIRouter()


class HistoryOriginBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (scope["path"].startswith("/api/comparisons") or scope["path"] in {"/api/system/database", "/api/ai/status"}):
            headers = dict(scope["headers"])
            origin = headers.get(b"origin")
            if (origin is not None and origin not in {b"http://127.0.0.1:8010", b"http://localhost:8010"}) or headers.get(b"sec-fetch-site") == b"cross-site":
                return await JSONResponse({"detail": {"code": "origin_rejected", "message": "Cross-origin history requests are not allowed."}}, status_code=403)(scope, receive, send)
        await self.app(scope, receive, send)


@router.get("/api/system/database", tags=["System"])
async def database_readiness(request: Request):
    return await run_in_threadpool(request.app.state.history.readiness)


@router.post("/api/comparisons", tags=["History"])
async def create_saved_comparison(request: Request):
    store = request.app.state.history
    await run_in_threadpool(store.readiness)
    result = await upload_pair(request, compare=True)
    record, created = await run_in_threadpool(store.save, result)
    return JSONResponse({**record, "reused": not created, "result": result}, status_code=201 if created else 200,
                        headers={"Location": "/api/comparisons/" + record["id"]})


@router.get("/api/comparisons", tags=["History"])
async def list_saved_comparisons(request: Request, limit: int = Query(default=20, ge=1, le=50), cursor: UUID | None = None):
    return await run_in_threadpool(request.app.state.history.list, limit, str(cursor) if cursor else None)


@router.get("/api/comparisons/{run_id}", tags=["History"])
async def saved_comparison(request: Request, run_id: UUID):
    return await run_in_threadpool(request.app.state.history.get, str(run_id))


@router.delete("/api/comparisons/{run_id}", tags=["History"], status_code=204)
async def delete_saved_comparison(request: Request, run_id: UUID):
    await run_in_threadpool(request.app.state.history.delete, str(run_id))
    request.app.state.explanations.forget(str(run_id))
    return Response(status_code=204)


@router.get("/api/comparisons/{run_id}/export", tags=["History"])
async def export_saved_comparison(request: Request, run_id: UUID, format: Literal["json", "markdown"] = "json"):
    record = await run_in_threadpool(request.app.state.history.get, str(run_id))
    exporter = json_export if format == "json" else markdown_export
    content = await run_in_threadpool(exporter, record)
    extension, media = ("json", "application/json") if format == "json" else ("md", "text/markdown")
    return Response(content, media_type=media, headers={
        "Content-Disposition": 'attachment; filename="comparison-' + str(run_id) + '.' + extension + '"',
        "Content-Security-Policy": "sandbox; default-src 'none'", "Referrer-Policy": "no-referrer",
    })
