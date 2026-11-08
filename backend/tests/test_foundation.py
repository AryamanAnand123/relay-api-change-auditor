import asyncio

import httpx

from auditor.main import create_app


def request(method, path, base_url="http://127.0.0.1"):
    async def perform():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url=base_url
        ) as client:
            return await client.request(method, path)

    return asyncio.run(perform())


def test_liveness_does_not_claim_unimplemented_readiness():
    response = request("GET", "/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "section": 7, "version": "0.7.0"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_unexpected_host_is_rejected():
    assert request("GET", "/health", base_url="http://unrelated.example").status_code == 400


def test_unknown_feature_routes_are_not_successful():
    assert request("POST", "/api/not-implemented").status_code == 404
    assert request("GET", "/api/system").json()["stage"] == "portfolio_ready"


def test_schema_has_only_current_operations_and_no_external_docs_assets():
    schema = request("GET", "/openapi.json").json()
    assert set(schema["paths"]) == {"/api/system", "/health", "/api/specifications/validate", "/api/specifications/compare", "/api/comparisons", "/api/comparisons/{run_id}", "/api/comparisons/{run_id}/export", "/api/system/database", "/api/examples/{name}", "/api/ai/status", "/api/comparisons/{run_id}/explanations"}
    assert request("GET", "/docs").status_code == 404
