import asyncio
from pathlib import Path

import httpx
import pytest

from auditor.config import Settings
from auditor.main import create_app


@pytest.fixture
def app(tmp_path):
    build = tmp_path / "frontend"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text('<!doctype html><title>Relay test</title><script src="/assets/app.js"></script>', encoding="utf-8")
    (build / "assets/app.js").write_text('document.title = "Relay";', encoding="utf-8")
    (build / "assets/app.css").write_text('body { color: black; }', encoding="utf-8")
    (build / "relay.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    (tmp_path / "private.txt").write_text("synthetic-outside-build", encoding="utf-8")
    result = create_app(Settings(_env_file=None, runtime_root=tmp_path / "runtime", frontend_dist=build))
    yield result
    result.state.history.close()


def request(app, path):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8010") as client:
            return await client.get(path)
    return asyncio.run(run())


def test_html_has_self_only_script_style_and_no_store(app):
    response = request(app, "/")
    assert response.status_code == 200 and "Relay test" in response.text
    assert response.headers["content-type"].startswith("text/html")
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "style-src 'self'" in response.headers["content-security-policy"]
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path,media", [("/assets/app.js", "text/javascript"), ("/assets/app.css", "text/css"), ("/relay.svg", "image/svg+xml")])
def test_built_assets_have_the_correct_content_type(app, path, media):
    response = request(app, path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media)


@pytest.mark.parametrize("path", ["/assets/missing.js", "/assets/%2e%2e%2f%2e%2e%2fprivate.txt", "/api/not-real", "/not-an-app-route", "/api/examples/README.md", "/api/examples/%2e%2e%2f.env"])
def test_missing_assets_and_unknown_api_paths_do_not_leak_or_become_spa_html(app, path):
    response = request(app, path)
    assert response.status_code == 404
    assert "synthetic-outside-build" not in response.text
    assert "Relay test" not in response.text


@pytest.mark.parametrize("name", ["orders-v1.json", "orders-v2-breaking.json", "orders-v2-compatible.json"])
def test_only_original_public_examples_are_available(app, name):
    response = request(app, "/api/examples/" + name)
    assert response.status_code == 200
    assert response.json()["openapi"] == "3.1.0"
    assert name in response.headers["content-disposition"]


def test_missing_frontend_build_is_actionable_but_api_still_runs(tmp_path):
    app = create_app(Settings(_env_file=None, runtime_root=tmp_path / "runtime", frontend_dist=tmp_path / "missing"))
    try:
        response = request(app, "/")
        assert response.status_code == 503 and "npm.cmd run build" in response.json()["detail"]
        assert request(app, "/assets/missing.js").status_code == 404
        assert request(app, "/health").status_code == 200
        assert request(app, "/api/system").json()["stage"] == "portfolio_ready"
    finally:
        app.state.history.close()
