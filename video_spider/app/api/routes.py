"""REST API + SSE 端点。"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .. import config, db, events
from ..downloader import daily_update, manager
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


# ---------------- 全站视频浏览（手机端） ----------------

def _find_video_file(category_name: str, video_key: str, roots: list[Path]) -> Path | None:
    """与下载保存逻辑一致：分类安全名子目录下按 mp4 优先探测。"""
    base = manager._safe_name(category_name)  # noqa: SLF001 - 同包内复用保存时的命名规则
    for root in roots:
        for ext in (".mp4", ".ts"):
            p = root / base / f"{video_key}{ext}"
            if p.is_file():
                return p
    return None


@router.get("/all-videos")
def get_all_videos(category_id: int | None = None, status: str | None = None,
                   q: str = "", page: int = Query(1, ge=1),
                   page_size: int = Query(24, ge=1, le=96)) -> dict:
    """跨分类全站视频列表（分页），供手机端浏览页使用。"""
    where = ["1=1"]
    params: list = []
    if category_id:
        where.append("v.category_id = ?")
        params.append(category_id)
    if status:
        where.append("v.status = ?")
        params.append(status)
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(v.title LIKE ? OR v.video_key LIKE ?)")
        params += [like, like]
    where_sql = " AND ".join(where)
    total = db.query_one(
        f"SELECT COUNT(*) AS n FROM videos v WHERE {where_sql}", tuple(params)
    )["n"]
    rows = db.query_all(
        f"""SELECT v.id, v.video_key, v.title, v.status, v.error,
                   v.cover_path, v.total_segments, v.updated_at,
                   v.category_id, c.name AS category_name
            FROM videos v JOIN categories c ON c.id = v.category_id
            WHERE {where_sql}
            ORDER BY v.updated_at DESC, v.id DESC
            LIMIT ? OFFSET ?""",
        tuple(params + [page_size, (page - 1) * page_size]),
    )
    roots = manager.video_roots()
    # 分片进度：对本页视频做一次 IN 聚合（videos 表没有 done_segments 列）
    seg_done: dict[int, int] = {}
    if rows:
        ph = ",".join("?" * len(rows))
        for s in db.query_all(
            f"SELECT video_id, SUM(status='done') AS done_n FROM segments "
            f"WHERE video_id IN ({ph}) GROUP BY video_id",
            tuple(r["id"] for r in rows),
        ):
            seg_done[s["video_id"]] = s["done_n"]
    items = []
    for r in rows:
        f = _find_video_file(r["category_name"], r["video_key"], roots)
        items.append({
            "id": r["id"],
            "video_key": r["video_key"],
            "title": r["title"] or r["video_key"],
            "status": r["status"],
            "category_id": r["category_id"],
            "category_name": r["category_name"],
            "cover": r["cover_path"].split("/")[-1] if r["cover_path"] else None,
            "ext": f.suffix.lstrip(".") if f else None,
            "size": f.stat().st_size if f else None,
            "done_segments": seg_done.get(r["id"], 0),
            "total_segments": r["total_segments"],
            "error": r["error"],
            "updated_at": r["updated_at"],
        })
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/video-file/{video_id}")
def get_video_file(video_id: int):
    """在线播放/下载：FileResponse 原生支持 Range，mp4 可拖进度条。"""
    row = db.query_one(
        """SELECT v.video_key, c.name AS category_name
           FROM videos v JOIN categories c ON c.id = v.category_id WHERE v.id = ?""",
        (video_id,),
    )
    if not row:
        raise HTTPException(404, "视频不存在")
    f = _find_video_file(row["category_name"], row["video_key"], manager.video_roots())
    if not f:
        raise HTTPException(404, "视频文件缺失")
    media = "video/mp4" if f.suffix == ".mp4" else "video/mp2t"
    return FileResponse(f, media_type=media, filename=f.name,
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/covers/{name}")
def get_cover(name: str):
    """视频封面（数据目录 covers/，文件名即 video_key）。"""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(404, "not found")
    f = config.COVER_DIR / name
    if not f.is_file():
        raise HTTPException(404, "封面不存在")
    return FileResponse(f, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


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


@router.post("/daily-update/run")
def run_daily_update() -> dict:
    """手动立即执行一次每日增量检查（与定时检查同一逻辑）。"""
    return daily_update.trigger_now()


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
        if k == "video_root_default":
            v = str(Path(str(v).strip())) if str(v).strip() else ""
            if v and manager.writable_free(Path(v), warn=False) is None:
                raise HTTPException(400, f"默认保存目录不可创建或不可写：{v}")
        if k == "daily_update_time":
            v = str(v).strip()
            if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", v):
                raise HTTPException(400, "时间格式应为 HH:MM，例如 04:00")
        db.set_setting(k, v)
    return {"settings": db.get_settings()}


# ---------------- 磁盘 / 保存位置 ----------------

@router.get("/disk")
def disk_info() -> dict:
    """所有候选保存目录及所在磁盘用量。

    save_path 为下次保存将使用的盘；default_root 为设置的固定默认盘（空 = 动态选盘）。
    """
    default_root = (db.get_settings().get("video_root_default") or "").strip()
    default_key = os.path.normcase(str(Path(default_root))) if default_root else ""
    disks = []
    for root in manager.video_roots():
        entry: dict = {"path": str(root), "total": 0, "used": 0,
                       "free": 0, "videos_size": 0, "error": None,
                       "writable": False, "is_default": os.path.normcase(str(root)) == default_key}
        try:
            root.mkdir(parents=True, exist_ok=True)
            du = shutil.disk_usage(root)
            entry["total"], entry["used"], entry["free"] = du.total, du.used, du.free
        except OSError as e:
            entry["error"] = str(e)  # 盘未挂载/已拔出：仍返回条目供前端展示
        else:
            entry["writable"] = manager.writable_free(root, warn=False) is not None
            for p in root.rglob("*"):
                try:
                    if p.is_file():
                        entry["videos_size"] += p.stat().st_size
                except OSError:  # noqa: BLE001 - 单个文件取不到大小不影响整体
                    continue
        disks.append(entry)
    settings = db.get_settings()
    return {"save_path": str(manager.choose_video_root()),
            "default_root": default_root,
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
