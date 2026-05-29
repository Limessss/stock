"""FastAPI 入口。

启动方式:
  cd backend
  uv run uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import multiprocessing as mp
import sys
from pathlib import Path

# 把仓库根加入 sys.path，以便 `import model.*`
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Windows 多进程回测/脚本入口需要
if sys.platform == "win32":
    mp.freeze_support()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import api_router, ws_router
from .core.config import settings
from .core.database import init_db
from .services.ws_manager import manager


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        docs_url="/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)
    app.include_router(ws_router)  # /ws/...

    @app.on_event("startup")
    async def _startup() -> None:
        init_db()
        manager.attach_loop(asyncio.get_running_loop())

    @app.get("/")
    def root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": f"{settings.api_prefix}/health",
        }

    return app


app = create_app()
