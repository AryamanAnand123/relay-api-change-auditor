"""Serve only the built local UI and three original public specification fixtures."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse

from auditor.config import PROJECT_ROOT

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
HTML_HEADERS = {"Content-Security-Policy": CSP, "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}
EXAMPLES = {name: PROJECT_ROOT / "examples" / name for name in ("orders-v1.json", "orders-v2-breaking.json", "orders-v2-compatible.json")}


def frontend_router(build_root: Path):
    router = APIRouter()
    build_root = build_root.resolve()

    @router.get("/", include_in_schema=False)
    async def index():
        path = build_root / "index.html"
        if not path.is_file():
            raise HTTPException(503, "Frontend not built. Run npm.cmd ci and npm.cmd run build from the frontend folder.")
        return FileResponse(path, media_type="text/html", headers=HTML_HEADERS)

    @router.get("/relay.svg", include_in_schema=False)
    async def favicon():
        path = build_root / "relay.svg"
        if not path.is_file():
            raise HTTPException(404, "Asset not found")
        return FileResponse(path, media_type="image/svg+xml", headers=HTML_HEADERS)

    @router.get("/assets/{asset_path:path}", include_in_schema=False)
    async def assets(asset_path: str):
        base = (build_root / "assets").resolve()
        try:
            path = (base / asset_path).resolve()
            if not path.is_relative_to(base) or not path.is_file():
                raise HTTPException(404, "Asset not found")
        except (ValueError, OSError):
            raise HTTPException(404, "Asset not found") from None
        media = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".woff2": "font/woff2"}.get(path.suffix)
        return FileResponse(path, media_type=media)

    @router.get("/api/examples/{name}", tags=["Examples"])
    async def example(name: str):
        path = EXAMPLES.get(name)
        if path is None or not path.is_file():
            raise HTTPException(404, "Example not found")
        return FileResponse(path, media_type="application/json", filename=name)

    return router
