"""REST API + SSE 端点。"""

from __future__ import annotations

import asyncio
import shutil
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db, events
from ..downloader import manager
from ..scraper import category_sync

router = APIRouter(prefix="/api")


# ---------------- 分类 ----------------

@router.get("/categories")
def get_categories() -> dict:
    return {"categories": db.list_categories()}


class SyncBody(BaseModel):
    with_counts: bool = True


@router.post("/categories/sync")
def sync_categories(body: SyncBody) -> dict:
    if category_sync.is_syncing():
        return {"ok": False, "message": "同步已在进行中"}
    threading.Thread(target=category_sync.run_sync, args=(body.with_counts,),
                     name="category-sync", daemon=True).start()
    return {"ok": True}


# ---------------- 视频 ----------------

@router.get("/videos")
def get_videos(category_id: int, status: str | None = None,
               limit: int = 200, offset: int = 0) -> dict:
    if limit > 1000:
        limit = 1000
    return {"videos": db.list_videos(category_id, status, limit, offset),
            "summary": db.video_status_summary(category_id)}


# ---------------- 任务 ----------------

@router.get("/tasks")
def get_tasks() -> dict:
    return {"tasks": db.list_tasks()}


class TaskBody(BaseModel):
    category_id: int
    thread_count: int | None = None


@router.post("/tasks")
def create_task(body: TaskBody) -> dict:
    threads = body.thread_count or int(db.get_settings().get("default_threads", "3"))
    threads = max(1, min(threads, 32))
    try:
        return {"task": manager.create_task(body.category_id, threads)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class TaskPatch(BaseModel):
    thread_count: int


@router.patch("/tasks/{task_id}")
def patch_task(task_id: int, body: TaskPatch) -> dict:
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    cat = db.get_category(task["category_id"])
    if cat and cat["type"] == "manual":
        raise HTTPException(400, "插件提交的下载队列固定单线程，不可调整")
    manager.resize_task(task_id, max(1, min(body.thread_count, 32)))
    return {"task": db.get_task(task_id)}


@router.post("/tasks/{task_id}/start")
def start_task(task_id: int) -> dict:
    _ensure(task_id)
    manager.start_task(task_id)
    return {"task": db.get_task(task_id)}


@router.post("/tasks/{task_id}/pause")
def pause_task(task_id: int) -> dict:
    _ensure(task_id)
    manager.pause_task(task_id)
    return {"task": db.get_task(task_id)}


@router.post("/tasks/{task_id}/stop")
def stop_task(task_id: int) -> dict:
    _ensure(task_id)
    manager.stop_task(task_id)
    return {"task": db.get_task(task_id)}


@router.post("/tasks/{task_id}/retry")
def retry_task(task_id: int) -> dict:
    _ensure(task_id)
    manager.retry_failed(task_id)
    return {"task": db.get_task(task_id)}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int) -> dict:
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["state"] == "running":
        raise HTTPException(400, "任务运行中，请先停止再删除")
    manager.delete_task(task_id)
    return {"ok": True}


def _ensure(task_id: int) -> None:
    if not db.get_task(task_id):
        raise HTTPException(404, "任务不存在")


# ---------------- 浏览器插件：手动提交 ----------------

class ManualBody(BaseModel):
    detail_url: str
    title: str | None = None


@router.post("/manual/submit")
def manual_submit(body: ManualBody) -> dict:
    try:
        return manager.submit_manual(body.detail_url.strip(),
                                     (body.title or "").strip() or None)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/manual/state")
def manual_state(detail_url: str) -> dict:
    return manager.manual_state(detail_url.strip())


# ---------------- 设置 ----------------

@router.get("/settings")
def get_settings() -> dict:
    return {"settings": db.get_settings()}


class SettingsBody(BaseModel):
    values: dict[str, Any]


@router.put("/settings")
def put_settings(body: SettingsBody) -> dict:
    allowed = set(db.get_settings())  # 只接受已知键
    for k, v in body.values.items():
        if k not in allowed:
            continue
        if k == "video_dir":
            v = str(v).strip()
            if v:
                try:
                    Path(v).mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    raise HTTPException(400, f"目录不可创建或不可写：{e}") from e
        if k == "video_dirs":
            lines = [ln.strip() for ln in str(v).splitlines() if ln.strip()]
            for d in lines:
                try:
                    Path(d).mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    raise HTTPException(400, f"目录不可创建或不可写：{e}") from e
            v = "\n".join(lines)
        db.set_setting(k, v)
    return {"settings": db.get_settings()}


# ---------------- 磁盘 / 保存位置 ----------------

@router.get("/disk")
def disk_info() -> dict:
    """所有候选保存目录及所在磁盘用量；save_path 为下次保存将使用的盘。"""
    disks = []
    for root in manager.video_roots():
        entry: dict = {"path": str(root), "total": 0, "used": 0,
                       "free": 0, "videos_size": 0, "error": None}
        try:
            root.mkdir(parents=True, exist_ok=True)
            du = shutil.disk_usage(root)
            entry["total"], entry["used"], entry["free"] = du.total, du.used, du.free
        except OSError as e:
            entry["error"] = str(e)  # 盘未挂载/已拔出：仍返回条目供前端展示
        else:
            for p in root.rglob("*"):
                try:
                    if p.is_file():
                        entry["videos_size"] += p.stat().st_size
                except OSError:  # noqa: BLE001 - 单个文件取不到大小不影响整体
                    continue
        disks.append(entry)
    settings = db.get_settings()
    return {"save_path": str(manager.choose_video_root()),
            "video_dir": settings.get("video_dir", ""),
            "video_dirs": settings.get("video_dirs", ""),
            "disks": disks}


# ---------------- SSE ----------------

@router.get("/events")
async def sse_events() -> StreamingResponse:
    return StreamingResponse(_event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


async def _event_stream():
    q = events.subscribe()
    try:
        yield "retry: 3000\n\n"
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=15.0)
                yield events.format_sse(msg)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    finally:
        events.unsubscribe(q)
