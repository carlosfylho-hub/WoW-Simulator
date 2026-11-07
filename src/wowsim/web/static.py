"""Serve the built React frontend (Simulator-WoW) from the FastAPI app.

The React app is built by Vite into ``Simulator-WoW/dist``. In production this
module mounts the static assets and adds an SPA fallback so client-side routes
work without a Node server. API routes registered before :func:`montar_frontend`
keep precedence because FastAPI matches routes in registration order.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..paths import PROJECT_ROOT

FRONTEND_DIST_ENV = "WOWSIM_FRONTEND_DIST"


def dist_dir() -> Path:
    """Locate the built React app. Override with ``WOWSIM_FRONTEND_DIST``."""
    explicit = os.environ.get(FRONTEND_DIST_ENV)
    if explicit:
        return Path(explicit).resolve()
    return (PROJECT_ROOT.parent / "Simulator-WoW" / "dist").resolve()


def montar_frontend(app: FastAPI) -> bool:
    """Mount assets and the SPA fallback. Returns True when mounted."""
    dist = dist_dir()
    index = dist / "index.html"
    if not index.is_file():
        return False

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path:
            candidate = (dist / full_path).resolve()
            # Keep serving confined to the dist directory.
            if candidate.is_file() and dist in candidate.parents:
                return FileResponse(candidate)
        return FileResponse(index)

    return True
