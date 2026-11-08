"""Bounded pair uploads, local request admission, and disposable validation."""

import asyncio
import json
import os
import subprocess
import sys

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import JSONResponse

from auditor.config import PROJECT_ROOT
from auditor.spec_input import BODY_LIMIT, FILE_LIMIT, OUTPUT_LIMIT, WORKER_TIMEOUT

router = APIRouter()
VALIDATE_PATH = "/api/specifications/validate"
COMPARE_PATH = "/api/specifications/compare"
SAVE_PATH = "/api/comparisons"


class UploadBoundary:
    """Limit bytes before multipart parsing; admit only one validation at a time."""

    def __init__(self, app):
        self.app = app
        self.lock = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in {VALIDATE_PATH, COMPARE_PATH, SAVE_PATH} or scope["method"] != "POST":
            return await self.app(scope, receive, send)

        async def reject(status, code, message):
            await JSONResponse({"detail": {"code": code, "message": message}}, status_code=status, headers={"Cache-Control": "no-store"})(scope, receive, send)

        headers = {key.lower(): value for key, value in scope["headers"]}
        # This unauthenticated local endpoint is not a cross-site upload service.
        if b"origin" in headers or headers.get(b"sec-fetch-site") == b"cross-site":
            origin = headers.get(b"origin", b"").decode("latin-1")
            if origin not in {"http://127.0.0.1:8010", "http://localhost:8010"}:
                return await reject(403, "origin_rejected", "Cross-origin uploads are not allowed.")
        if headers.get(b"content-encoding", b"identity").lower() != b"identity":
            return await reject(415, "unsupported_encoding", "Compressed request bodies are not supported.")
        if b"content-length" in headers:
            try:
                length = int(headers[b"content-length"])
                if length < 0:
                    raise ValueError
            except ValueError:
                return await reject(400, "invalid_length", "Content-Length must be a nonnegative integer.")
            if length > BODY_LIMIT:
                return await reject(413, "request_too_large", "Upload body exceeds the two-file limit plus multipart overhead.")
        if self.lock.locked():
            return await reject(429, "validation_busy", "Another specification pair is being processed. Try again shortly.")
        async with self.lock:
            content = bytearray()
            try:
                async with asyncio.timeout(10):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        content.extend(message.get("body", b""))
                        if len(content) > BODY_LIMIT:
                            return await reject(413, "request_too_large", "Upload body exceeds the supported limit.")
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(408, "upload_timeout", "Upload did not finish within 10 seconds.")
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(content), "more_body": False}
                return await receive()

            await self.app(scope, bounded_receive, send)


async def run_validation(payload, compare=False):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "backend")
    environment["PYTHONIOENCODING"] = "utf-8"
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "auditor.spec_worker",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT), env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except OSError:
        raise HTTPException(503, {"code": "worker_unavailable", "message": "Could not start the isolated specification worker."}) from None
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(json.dumps({**payload, "_compare": compare}).encode("utf-8")), timeout=WORKER_TIMEOUT)
    except (TimeoutError, asyncio.CancelledError) as error:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        if isinstance(error, asyncio.CancelledError):
            raise
        raise HTTPException(422, {"code": "validation_timeout", "message": "Validation exceeded its 10-second budget; simplify the specification."}) from None
    if process.returncode != 0 or len(stdout) > OUTPUT_LIMIT:
        raise HTTPException(503, {"code": "worker_failed", "message": "Specification worker could not complete."})
    try:
        outcome = json.loads(stdout)
    except (ValueError, UnicodeError):
        raise HTTPException(503, {"code": "worker_failed", "message": "Specification worker returned an invalid result."}) from None
    if isinstance(outcome, dict) and outcome.get("ok") is False:
        error = outcome.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str) and isinstance(error.get("message"), str):
            raise HTTPException(503 if error["code"] == "validation_failed" else 422, error)
    if isinstance(outcome, dict) and outcome.get("ok") is True:
        result = outcome.get("result")
        if isinstance(result, dict) and result.get("status") == ("compared" if compare else "validated") and result.get("comparison_performed") is compare and isinstance(result.get("old"), dict) and isinstance(result.get("new"), dict):
            if not compare or isinstance(result.get("comparison"), dict):
                return result
    raise HTTPException(503, {"code": "worker_failed", "message": "Specification worker returned an invalid result."})


@router.post(VALIDATE_PATH, tags=["Specifications"])
async def validate_pair(request: Request):
    return await upload_pair(request)


@router.post(COMPARE_PATH, tags=["Specifications"])
async def compare_pair(request: Request):
    return await upload_pair(request, compare=True)


async def upload_pair(request: Request, compare=False):
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(415, {"code": "multipart_required", "message": "Upload JSON files as multipart fields named old and new."})
    parser = MultiPartParser(request.headers, request.stream(), max_files=2, max_fields=0, max_part_size=FILE_LIMIT)
    # The boundary already caps the whole request. Keep these bounded files in
    # memory instead of writing private specs to the shared Windows temp folder.
    parser.spool_max_size = BODY_LIMIT + 1
    try:
        form = await parser.parse()
    except (MultiPartException, ValueError):
        raise HTTPException(422, {"code": "invalid_multipart", "message": "Supply exactly two JSON files using fields old and new."}) from None
    try:
        entries = form.multi_items()
        if len(entries) != 2 or {name for name, _ in entries} != {"old", "new"}:
            raise HTTPException(422, {"code": "invalid_fields", "message": "Supply exactly one old file and one new file."})
        payload = {}
        for side, upload in entries:
            if not isinstance(upload, UploadFile) or not upload.filename or not upload.filename.lower().endswith(".json") or len(upload.filename) > 255:
                raise HTTPException(422, {"code": "json_file_required", "message": "Each field must contain a .json file with a filename of at most 255 characters.", "side": side})
            raw = await upload.read(FILE_LIMIT + 1)
            if len(raw) > FILE_LIMIT:
                raise HTTPException(413, {"code": "file_too_large", "message": "Each specification must be at most 2 MiB.", "side": side})
            try:
                payload[side] = raw.decode("utf-8")
            except UnicodeError:
                raise HTTPException(422, {"code": "invalid_encoding", "message": "Specifications must be UTF-8 JSON.", "side": side}) from None
        return await run_validation(payload, compare=True) if compare else await run_validation(payload)
    finally:
        await form.close()
