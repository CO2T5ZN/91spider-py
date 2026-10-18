"""FastAPI 应用组装：初始化 DB / SSE / 任务恢复，托管前端静态资源（SPA 回退）。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, events
from .api.routes import router
from .downloader import manager

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s")
logging.getLogger("spider").setLevel(logging.INFO)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    events.init(asyncio.get_running_loop())
    manager.recover()
    yield


app = FastAPI(title="video-spider", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router)

# 前端构建产物（frontend/dist）：/assets 走静态文件，其余路径回退 index.html（SPA 路由）
_DIST = Path(config.FRONTEND_DIST)
if _DIST.is_dir():
    if (_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = (_DIST / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(_DIST.resolve())):
            return FileResponse(candidate)
        # index.html 禁缓存，避免 SPA 壳陈旧引用已被替换的 bundle
        return FileResponse(_DIST / "index.html",
                            headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
