"""只读数据库访问：与 video_spider 共用 spider.db（WAL，只读连接不阻塞下载机写入）。"""

from __future__ import annotations

import sqlite3

from . import config


def connect() -> sqlite3.Connection:
    """每请求一个只读连接（mode=ro），Row 工厂方便转 dict。"""
    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def get_settings() -> dict[str, str]:
    return {r["key"]: r["value"] for r in query_all("SELECT key, value FROM settings")}
