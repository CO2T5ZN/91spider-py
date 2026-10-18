"""路径解析：视频保存根目录（跟随 spider 的 settings.video_dir）与视频文件探测。"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from . import config, db

_UNSAFE = re.compile(r'[\\/:*?"<>|]')

# 视频文件探测缓存：数据盘（机械盘）与下载写入共用，繁忙时一次 stat 都可能卡数秒。
# 策略：首次探测同步做；之后永远秒回缓存值，TTL 过期由后台线程刷新（stale-while-revalidate），
# 保证翻页请求绝不因盘繁忙而卡顿。
_file_cache: dict[str, tuple[float, Path | None]] = {}
_file_cache_lock = threading.Lock()
_refreshing: set[str] = set()
_FILE_TTL = 60.0


def safe_name(name: str) -> str:
    """与 video_spider manager._safe_name 保持一致：分类名 → 目录名。"""
    return _UNSAFE.sub("", name).strip() or "unknown"


def video_roots() -> list[Path]:
    """候选视频保存根目录（多硬盘支持，跟随 spider 的 settings）。

    优先级：settings.video_dirs（每行/分号一个）> 旧 settings.video_dir > 默认 DATA_DIR/videos。
    """
    settings = db.get_settings()
    roots: list[Path] = []
    raw = (settings.get("video_dirs") or "").strip()
    if raw:
        for line in re.split(r"[\r\n;]+", raw):
            line = line.strip()
            if line:
                roots.append(Path(line))
    val = (settings.get("video_dir") or "").strip()
    if val:
        roots.append(Path(val))
    roots.append(config.DATA_DIR / "videos")
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        k = str(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _probe(roots: list[Path], category_name: str, video_key: str) -> Path | None:
    """在所有候选根目录下探测视频文件（移动硬盘可能挂载点变化，逐根找）。"""
    base = safe_name(category_name)
    for root in roots:
        for ext in (".mp4", ".ts"):
            p = root / base / f"{video_key}{ext}"
            if p.is_file():
                return p
    return None


def _refresh(cache_key: str, roots: list[Path], category_name: str, video_key: str) -> None:
    try:
        f = _probe(roots, category_name, video_key)
        with _file_cache_lock:
            _file_cache[cache_key] = (time.monotonic(), f)
    finally:
        with _file_cache_lock:
            _refreshing.discard(cache_key)


def find_video_file(category_name: str, video_key: str) -> Path | None:
    roots = video_roots()
    cache_key = f"{'|'.join(str(r) for r in roots)}|{safe_name(category_name)}|{video_key}"
    now = time.monotonic()
    with _file_cache_lock:
        hit = _file_cache.get(cache_key)
    if hit is None:
        # 首次见到的条目：同步探测一次
        f = _probe(roots, category_name, video_key)
        with _file_cache_lock:
            _file_cache[cache_key] = (now, f)
        return f
    if now - hit[0] >= _FILE_TTL and cache_key not in _refreshing:
        with _file_cache_lock:
            _refreshing.add(cache_key)
        threading.Thread(target=_refresh, args=(cache_key, roots, category_name, video_key),
                         daemon=True).start()
    return hit[1]  # 立即返回（可能是旧值），后台刷新


def warm_recent(limit: int = 5000) -> None:
    """启动后台预热：为最近的任务视频填充文件缓存，避免重启后首批请求撞盘。"""

    def run():
        time.sleep(1.0)
        try:
            rows = db.query_all(
                """SELECT v.video_key, c.name AS cat FROM videos v
                   JOIN categories c ON c.id = v.category_id
                   WHERE v.status = 'done'
                   ORDER BY v.updated_at DESC, v.id DESC LIMIT ?""", (limit,))
            for r in rows:
                find_video_file(r["cat"], r["video_key"])
                time.sleep(0.05)
            log = __import__("logging").getLogger("gallery.paths")
            log.info("文件路径预热完成：%d 条", len(rows))
        except Exception as e:  # noqa: BLE001
            print(f"预热异常: {e}")

    threading.Thread(target=run, name="filepath-warm", daemon=True).start()
