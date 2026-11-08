"""Same-origin, size-bounded, explicit-consent AI API for saved reports."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError
from starlette.concurrency import run_in_threadpool

from auditor.explanations import AIError

router = APIRouter()


class ExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    finding_id: str = Field(min_length=1, max_length=100)
    allow_external_processing: StrictBool


@router.get("/api/ai/status", tags=["AI explanations"])
async def ai_status(request: Request):
    return request.app.state.explanations.status()


@router.post("/api/comparisons/{run_id}/explanations", tags=["AI explanations"])
async def explain(request: Request, run_id: UUID):
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, {"code": "json_required", "message": "Send an explicit JSON explanation request."})
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise HTTPException(415, {"code": "unsupported_encoding", "message": "Compressed requests are unsupported."})
    data = bytearray()
    try:
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 1024:
                    raise HTTPException(413, {"code": "ai_request_too_large", "message": "Explanation requests must be at most 1 KiB."})
        payload = ExplanationRequest.model_validate_json(bytes(data))
    except TimeoutError:
        raise HTTPException(408, {"code": "ai_request_timeout", "message": "Explanation request timed out."}) from None
    except (ValidationError, ValueError):
        raise HTTPException(422, {"code": "invalid_ai_request", "message": "Supply a finding_id and explicit allow_external_processing boolean only."}) from None
    if not payload.allow_external_processing:
        raise HTTPException(422, {"code": "consent_required", "message": "Confirm sending this finding's bounded evidence to Groq before requesting an explanation."})
    store, service = request.app.state.history, request.app.state.explanations
    record = await run_in_threadpool(store.get, str(run_id))
    try:
        response = await service.generate(record, payload.finding_id)
        # A comparison deleted during inference must not regain cached private data.
        current = await run_in_threadpool(store.get, str(run_id))
        service.remember(current, payload.finding_id, response)
        return response
    except AIError as error:
        raise HTTPException(error.status, {"code": error.code, "message": error.message}) from None
