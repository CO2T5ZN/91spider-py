"""路径解析：视频保存根目录（跟随 spider 的 settings.video_dir）与视频文件探测。"""

from __future__ import annotations

import re

from . import config, db

_UNSAFE = re.compile(r'[\\/:*?"<>|]')


def safe_name(name: str) -> str:
    """与 video_spider manager._safe_name 保持一致：分类名 → 目录名。"""
    return _UNSAFE.sub("", name).strip() or "unknown"


def video_root() -> object:
    """视频保存根目录：spider settings.video_dir 非空则用之，否则 DATA_DIR/videos。

    与 spider 一样每次实时读取，下载机切换保存位置后无需重启本服务。
    """
    val = (db.get_settings().get("video_dir") or "").strip()
    from pathlib import Path

    return Path(val) if val else config.DATA_DIR / "videos"


def find_video_file(category_name: str, video_key: str) -> object | None:
    """在视频根目录/分类目录下按 mp4→ts 顺序探测文件；不存在返回 None。"""
    from pathlib import Path

    path = Path(video_root()) / safe_name(category_name)
    for ext in (".mp4", ".ts"):
        f = path / f"{video_key}{ext}"
        if f.is_file():
            return f
    return None
