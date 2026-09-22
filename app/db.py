"""只读数据库访问：与 video_spider 共用 spider.db（WAL，只读连接不阻塞下载机写入）。"""

from __future__ import annotations

import sqlite3
import threading
import time

from . import config

# 每线程复用一个只读连接（避免每请求重开连接；线程数受 FastAPI 线程池约束，不会泄漏）
_local = threading.local()

# settings 变化极少，短 TTL 缓存，省掉每条视频路径解析时的重复查询
_settings_cache: dict = {"t": 0.0, "v": {}}
_SETTINGS_TTL = 5.0


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=10,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in connect().execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    row = connect().execute(sql, params).fetchone()
    return dict(row) if row else None


def get_settings() -> dict[str, str]:
    now = time.monotonic()
    if now - _settings_cache["t"] > _SETTINGS_TTL:
        _settings_cache["v"] = {r["key"]: r["value"]
                                for r in query_all("SELECT key, value FROM settings")}
        _settings_cache["t"] = now
    return _settings_cache["v"]
