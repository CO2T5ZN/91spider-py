"""video-gallery：video_spider 下载视频的展示站（只读共用数据库与文件）。"""

from __future__ import annotations

import html
import json
import logging
import mimetypes
import os
import shutil
import subprocess
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
db.start_snapshot()  # 启动定期快照：查询走本地 SSD 上的库副本，避开机械盘 I/O 风暴
db.warm_pages()      # 首个快照生成后预热数据库页缓存（后台线程）


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


def _cover_mtime(name: str) -> int:
    """封面源文件的 mtime，用作 ?v= 版本号：同名封面被替换后 URL 变化，绕开长缓存。

    只 stat 源目录（判重后重生成会原地覆盖同名文件，mtime 即内容版本）；
    stat 失败回退 0，URL 退化为不带版本但仍然可用。
    """
    try:
        return int((config.COVER_DIR / name).stat().st_mtime)
    except OSError:
        return 0


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
        cover_name = r["cover_path"].split("/")[-1] if r["cover_path"] else None
        items.append({
            "id": r["id"],
            "title": r["title"] or r["video_key"],
            "video_key": r["video_key"],
            "tags": parse_tags(r["tags"]),
            "category_id": r["category_id"],
            "category_name": r["category_name"],
            "cover_url": f"/covers/{cover_name}?v={_cover_mtime(cover_name)}" if cover_name else None,
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


# ---------------- TS 时长探测（ffprobe + JSON 文件缓存）----------------
# mpegts.js 对 VOD 点播只在拿到总时长后才能显示进度条并精确 Range 拖动；
# TS 容器没有头部长度信息，大文件预载一段也推不出来，必须外部提供。
# ffprobe 只读容器头/尾，一次探测 <1s，结果按 video_id 缓存到本地 JSON。

_DURATION_LOCK = threading.Lock()
_DURATION_CACHE: dict[str, float] = {}
_DURATION_CACHE_FILE = Path(os.environ.get(
    "GALLERY_DURATION_CACHE", Path(__file__).resolve().parent.parent / ".duration-cache.json"))


def _load_duration_cache() -> None:
    try:
        data = json.loads(_DURATION_CACHE_FILE.read_text("utf-8"))
        if isinstance(data, dict):
            _DURATION_CACHE.update({k: v for k, v in data.items() if isinstance(v, (int, float))})
    except (OSError, ValueError):
        pass


def _save_duration_cache() -> None:
    try:
        tmp = _DURATION_CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_DURATION_CACHE), "utf-8")
        os.replace(tmp, _DURATION_CACHE_FILE)
    except OSError as e:  # noqa: BLE001 - 缓存写失败不影响返回结果
        log.warning("时长缓存写入失败: %s", e)


@app.get("/api/duration/{video_id}")
def video_duration(video_id: int):
    key = str(video_id)
    with _DURATION_LOCK:
        if key in _DURATION_CACHE:
            return {"duration": _DURATION_CACHE[key]}
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
    duration = None
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(f)],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(r.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:  # noqa: BLE001
        # 无 ffprobe / 探测失败：返回 null，前端按无时长降级（进度条不可拖远端）
        log.info("ffprobe 探测时长失败 %s: %s", f.name, e)
    if duration:
        with _DURATION_LOCK:
            _DURATION_CACHE[key] = duration
            _save_duration_cache()
    return {"duration": duration}


# 移动端「新标签页播放」页：全屏 xgplayer（内置移动端手势/倍速；TS 经 mpegts.js 在线播）。
# 播放器库从 /vendor/ 引用，由 frontend/scripts/copy-vendor.mjs 在构建时复制进 dist
_WATCH_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<link rel="stylesheet" href="/vendor/xgplayer.min.css">
<style>
  html,body{{margin:0;padding:0;height:100%;background:#000;color:#ddd;font-family:system-ui,sans-serif}}
  /* dvh 跟随移动端地址栏收展；100vh 是"大视口"，地址栏展开时比可见区域高，
     会让视频底部（进度条）被挤出屏幕 */
  body{{height:100vh;height:100dvh;display:flex;flex-direction:column;
        padding-bottom:env(safe-area-inset-bottom,0px)}}
  header{{flex:0 0 auto;display:flex;align-items:center;gap:12px;padding:8px 14px}}
  header .back{{flex:0 0 auto;display:flex;align-items:center;justify-content:center;
                width:34px;height:34px;margin-left:-8px;color:#ddd;font-size:22px;
                line-height:1;cursor:pointer;-webkit-tap-highlight-color:transparent;
                border-radius:50%;background:rgba(255,255,255,.08)}}
  header .back:active{{background:rgba(255,255,255,.2)}}
  header .t{{flex:1 1 auto;min-width:0;font-size:14px;color:#bbb;line-height:1.4;
             white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  header a{{flex:0 0 auto;color:#1677ff;text-decoration:none;font-size:13px}}
  /* 播放区占满剩余高度，高视口时居中、上下自然留空 */
  .stage{{flex:1 1 auto;min-height:0;position:relative;display:flex;flex-direction:column;
          justify-content:center;padding-bottom:12px}}
  .warn{{margin:auto;padding:40px 20px;text-align:center}}
  .warn a{{color:#1677ff}}
</style></head><body>
{body}
<script src="/vendor/xgplayer.min.js"></script>
<script src="/vendor/mpegts.js"></script>
<script src="/vendor/mpegts-plugin.js"></script>
<script>
// 返回列表页：本页是列表页 window.open 出来的新标签，优先直接关掉回到列表；
// 直接打开（书签/分享链接）时退而求其次走历史返回
window.goBack = function () {{
  window.close();
  setTimeout(function () {{
    if (!window.closed && history.length > 1) history.back();
  }}, 150);
}};
(function () {{
  var stage = document.querySelector('.stage');
  if (!stage) return;  // 文件缺失等无播放场景
  var data = {{ url: '{url}', poster: '{poster}', isTs: {is_ts}, id: {vid} }};
  var warn = function (msg) {{
    stage.innerHTML = '<div class="warn">' + msg +
      '，<a href="' + data.url + '" download>下载文件</a></div>';
  }};
  if (data.isTs && !(window.mpegts && mpegts.isSupported())) {{
    warn('当前浏览器不支持 TS 在线播放');
    return;
  }}
  var cap = Math.max(stage.clientHeight - 16, 180);
  var create = function (duration) {{
    var player = new xgplayer({{
      id: 'player', url: data.url, poster: data.poster,
      width: '100%', height: cap,
      videoFillMode: 'contain',
      autoplay: true, playsinline: true, lang: 'zh-cn',
      tsDuration: duration,  // MpegtsPlugin 读取：VOD 有了总时长才能拖动进度条
      plugins: data.isTs ? [window.MpegtsPlugin] : []
    }});
    player.on('error', function () {{ warn('在线播放失败'); }});
  }};
  if (!data.isTs) {{ create(null); return; }}
  // TS：先取 ffprobe 探测的总时长（后端有缓存，一次 <1s），失败则降级为无时长
  fetch('/api/duration/' + data.id).then(function (r) {{ return r.ok ? r.json() : null }})
    .then(function (d) {{ create(d && d.duration || null) }})
    .catch(function () {{ create(null) }});
}})();
</script>
</body></html>"""


@app.get("/watch/{video_id}")
def watch_page(video_id: int):
    v = db.query_one(
        """SELECT v.id, v.title, v.video_key, v.cover_path, c.name AS category_name
           FROM videos v JOIN categories c ON c.id = v.category_id WHERE v.id = ?""",
        (video_id,),
    )
    if not v:
        raise HTTPException(404, "视频不存在")
    title = (v["title"] or v["video_key"])[:80]
    f = paths.find_video_file(v["category_name"], v["video_key"])
    if f:
        url = f"/api/video-file/{video_id}"
        cover_name = v["cover_path"].split("/")[-1] if v["cover_path"] else None
        poster = f"/covers/{cover_name}?v={_cover_mtime(cover_name)}" if cover_name else ""
        is_ts = "true" if f.suffix == ".ts" else "false"
        body = ('<header><span class="back" onclick="goBack()">←</span>'
                '<span class="t">' + html.escape(title) + '</span>'
                f'<a href="{url}" download>下载</a></header>'
                '<div class="stage"><div id="player"></div></div>')
    else:
        url, poster, is_ts = "", "", "false"
        body = '<div class="warn">视频文件缺失</div>'
    return HTMLResponse(_WATCH_HTML.format(
        title=html.escape(title), body=body, url=url, poster=poster, is_ts=is_ts,
        vid=video_id))


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
