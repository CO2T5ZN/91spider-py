"""video-gallery：video_spider 下载视频的展示站（只读共用数据库与文件）。"""

from __future__ import annotations

import json
import logging
import mimetypes
import shutil
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gallery")

app = FastAPI(title="video-gallery", docs_url=None, redoc_url=None)

paths.warm_recent()  # 启动即预热最近视频的文件路径缓存（后台线程）


# ---------------- 封面：SSD 缓存 + 回源复制 + 后台预热 ----------------

def _safe_cover_name(name: str) -> str | None:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    return name


def _cover_in_cache(name: str) -> Path:
    src = config.COVER_DIR / name
    dst = config.COVER_CACHE_DIR / name
    if dst.is_file() and dst.stat().st_size > 0:
        return dst
    if not src.is_file():
        return dst
    config.COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    try:
        shutil.copyfile(src, tmp)
        tmp.replace(dst)
    except OSError as e:  # noqa: BLE001 - 复制失败（盘忙/消失）按 404 处理
        log.warning("封面回源复制失败 %s: %s", name, e)
        tmp.unlink(missing_ok=True)
        return src
    return dst


def _prewarm_covers() -> None:
    """后台把数据目录的新封面逐步复制进本地缓存，避免请求时撞机械盘写高峰。"""
    time.sleep(15)  # 错开启动时的文件路径预热，降低对机械盘的瞬时压力
    while True:
        try:
            if config.COVER_DIR.is_dir():
                config.COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                for src in config.COVER_DIR.iterdir():
                    if not src.is_file():
                        continue
                    dst = config.COVER_CACHE_DIR / src.name
                    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                        tmp = dst.with_suffix(dst.suffix + ".part")
                        try:
                            shutil.copyfile(src, tmp)
                            tmp.replace(dst)
                            time.sleep(0.2)  # 温和复制，不与下载抢盘
                        except OSError:
                            tmp.unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001
            log.warning("封面预热异常: %s", e)
        time.sleep(120)


@app.get("/covers/{name}")
def covers(name: str):
    clean = _safe_cover_name(name)
    if not clean:
        raise HTTPException(404, "not found")
    f = _cover_in_cache(clean)
    if not f.is_file():
        raise HTTPException(404, "cover not found")
    media_type = mimetypes.guess_type(clean)[0] or "image/jpeg"
    # 封面按 video_key 命名、生成后不再变化，浏览器可长缓存
    return FileResponse(f, media_type=media_type,
                        headers={"Cache-Control": "public, max-age=604800, immutable"})


threading.Thread(target=_prewarm_covers, name="cover-prewarm", daemon=True).start()


def parse_tags(raw: str | None) -> list[str]:
    try:
        v = json.loads(raw) if raw else []
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


@app.get("/api/categories")
def categories() -> dict:
    rows = db.query_all(
        """SELECT c.id, c.name, c.type, c.group_name, COUNT(v.id) AS count
           FROM categories c JOIN videos v ON v.category_id = c.id AND v.status = 'done'
           GROUP BY c.id ORDER BY count DESC, c.name"""
    )
    return {"categories": rows}


@app.get("/api/videos")
def videos(
    category_id: int | None = None,
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=96),
) -> dict:
    where = ["v.status = 'done'"]
    params: list = []
    if category_id:
        where.append("v.category_id = ?")
        params.append(category_id)
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(v.title LIKE ? ESCAPE '\\' OR v.video_key LIKE ? ESCAPE '\\')")
        esc = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{esc}%"
        params += [like, like]
    where_sql = " AND ".join(where)

    total = db.query_one(
        f"SELECT COUNT(*) AS n FROM videos v WHERE {where_sql}", tuple(params)
    )["n"]
    rows = db.query_all(
        f"""SELECT v.id, v.title, v.video_key, v.cover_path, v.tags, v.updated_at,
                   v.category_id, c.name AS category_name
            FROM videos v JOIN categories c ON c.id = v.category_id
            WHERE {where_sql}
            ORDER BY v.updated_at DESC, v.id DESC
            LIMIT ? OFFSET ?""",
        tuple(params + [page_size, (page - 1) * page_size]),
    )
    items = []
    for r in rows:
        f = paths.find_video_file(r["category_name"], r["video_key"])
        items.append({
            "id": r["id"],
            "title": r["title"] or r["video_key"],
            "video_key": r["video_key"],
            "tags": parse_tags(r["tags"]),
            "category_id": r["category_id"],
            "category_name": r["category_name"],
            "cover_url": f"/covers/{r['cover_path'].split('/')[-1]}" if r["cover_path"] else None,
            "ext": f.suffix.lstrip(".") if f else None,
            "size": f.stat().st_size if f else None,
            "updated_at": r["updated_at"],
        })
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/api/video-file/{video_id}")
def video_file(video_id: int):
    v = db.query_one(
        """SELECT v.video_key, v.category_id, c.name AS category_name
           FROM videos v JOIN categories c ON c.id = v.category_id WHERE v.id = ?""",
        (video_id,),
    )
    if not v:
        raise HTTPException(404, "视频不存在")
    f = paths.find_video_file(v["category_name"], v["video_key"])
    if not f:
        raise HTTPException(404, "视频文件缺失")
    # FileResponse 原生处理 Range 头（206 分段），浏览器可拖进度条
    return FileResponse(f, media_type=_media_type(f.suffix), filename=f.name,
                        headers={"Cache-Control": "public, max-age=86400"})


def _media_type(suffix: str) -> str:
    return {".mp4": "video/mp4", ".ts": "video/mp2t"}.get(suffix, "application/octet-stream")


# 移动端「新标签页播放」页：极简全屏视频页（无 SPA 依赖）
_WATCH_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<style>
  html,body{{margin:0;padding:0;background:#000;color:#ddd;font-family:system-ui,sans-serif}}
  header{{padding:8px 14px;font-size:14px;line-height:1.4;color:#bbb;
          white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  video{{display:block;width:100vw;max-height:calc(100vh - 42px);object-fit:contain;background:#000}}
  .warn{{padding:40px 20px;text-align:center}}
  .warn a{{color:#1677ff}}
</style></head><body>
{body}
</body></html>"""


@app.get("/watch/{video_id}")
def watch_page(video_id: int):
    v = db.query_one(
        """SELECT v.id, v.title, v.video_key, v.category_id, c.name AS category_name
           FROM videos v JOIN categories c ON c.id = v.category_id WHERE v.id = ?""",
        (video_id,),
    )
    if not v:
        raise HTTPException(404, "视频不存在")
    title = (v["title"] or v["video_key"])[:80]
    f = paths.find_video_file(v["category_name"], v["video_key"])
    if not f:
        body = '<div class="warn">视频文件缺失</div>'
    elif f.suffix == ".ts":
        body = (f'<div class="warn">TS 格式不支持网页播放，'
                f'<a href="/api/video-file/{video_id}" download>下载文件</a></div>')
    else:
        body = (f'<header>{title}</header>'
                f'<video controls autoplay playsinline src="/api/video-file/{video_id}"></video>')
    return HTMLResponse(_WATCH_HTML.format(title=title, body=body))


# ---------------- 前端静态托管（SPA 回退，放最后注册） ----------------

from pathlib import Path  # noqa: E402

_DIST = Path(config.FRONTEND_DIST)
if _DIST.is_dir():
    if (_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = (_DIST / full_path).resolve()
        if full_path and candidate.is_file() and str(candidate).startswith(str(_DIST.resolve())):
            return FileResponse(candidate)
        # index.html 严禁缓存（no-store），避免 SPA 壳陈旧引用已被替换的 bundle
        return FileResponse(_DIST / "index.html",
                            headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
