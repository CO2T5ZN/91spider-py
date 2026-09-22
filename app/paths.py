"""路径解析：视频保存根目录（跟随 spider 的 settings.video_dir）与视频文件探测。"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from . import config, db

_UNSAFE = re.compile(r'[\\/:*?"<>|]')

# 视频文件探测结果缓存：视频文件落盘后路径不变，缓存可让翻页完全不碰
# 数据盘（机械盘与下载写入共用，繁忙时一次 stat 也可能卡数秒）
_file_cache: dict[str, tuple[float, Path | None]] = {}
_file_cache_lock = threading.Lock()
_FILE_TTL = 60.0


def safe_name(name: str) -> str:
    """与 video_spider manager._safe_name 保持一致：分类名 → 目录名。"""
    return _UNSAFE.sub("", name).strip() or "unknown"


def video_root() -> Path:
    """视频保存根目录：spider settings.video_dir 非空则用之，否则默认 DATA_DIR/videos。

    实时读 settings（有短 TTL 缓存），下载机切换保存位置后无需重启本服务。
    """
    val = (db.get_settings().get("video_dir") or "").strip()
    return Path(val) if val else config.DATA_DIR / "videos"


def find_video_file(category_name: str, video_key: str) -> Path | None:
    """在视频根目录/分类目录下按 mp4→ts 顺序探测文件；不存在返回 None。

    结果带 TTL 缓存：同一进程内 60 秒内重复探测直接用缓存。
    """
    root = str(video_root())
    cache_key = f"{root}|{safe_name(category_name)}|{video_key}"
    now = time.monotonic()
    with _file_cache_lock:
        hit = _file_cache.get(cache_key)
        if hit and now - hit[0] < _FILE_TTL:
            return hit[1]
    f = None
    base = Path(root) / safe_name(category_name)
    for ext in (".mp4", ".ts"):
        p = base / f"{video_key}{ext}"
        if p.is_file():
            f = p
            break
    with _file_cache_lock:
        _file_cache[cache_key] = (now, f)
        # 简单防膨胀：超过 1 万条时清掉过期项
        if len(_file_cache) > 10000:
            for k in [k for k, v in _file_cache.items() if now - v[0] >= _FILE_TTL]:
                _file_cache.pop(k, None)
    return f
