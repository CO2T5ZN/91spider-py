"""只读数据库访问：与 video_spider 共用 spider.db（WAL，只读连接不阻塞下载机写入）。

数据盘（机械盘）与下载写入共用，繁忙时冷读一次页可能卡数秒，因此：
- 全进程共用一个只读连接（全局锁串行；查询都是毫秒级，串行无碍），
  其 SQLite 页缓存跨请求共享，热页常驻内存后查询零磁盘 I/O；
- cache_size 调大（32MB）足够装下整库。
"""

from __future__ import annotations

import sqlite3
import threading
import time

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

# settings 变化极少，短 TTL 缓存，省掉每条视频路径解析时的重复查询
_settings_cache: dict = {"t": 0.0, "v": {}}
_SETTINGS_TTL = 5.0


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True,
                               timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA cache_size=-32000")   # 32MB 页缓存
        conn.execute("PRAGMA mmap_size=134217728")  # 128MB mmap，读页零拷贝
        _conn = conn
    return _conn


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _connect().execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    with _lock:
        row = _connect().execute(sql, params).fetchone()
        return dict(row) if row else None


def get_settings() -> dict[str, str]:
    now = time.monotonic()
    if now - _settings_cache["t"] > _SETTINGS_TTL:
        _settings_cache["v"] = {r["key"]: r["value"]
                                for r in query_all("SELECT key, value FROM settings")}
        _settings_cache["t"] = now
    return _settings_cache["v"]


def warm_pages() -> None:
    """启动后台预热：把常用表整表读一遍，将 DB 页拉进连接缓存。"""

    def run():
        time.sleep(0.5)
        try:
            with _lock:
                c = _connect()
                c.execute("SELECT id, video_key, title, tags, cover_path, status, "
                          "updated_at, category_id FROM videos").fetchall()
                c.execute("SELECT * FROM categories").fetchall()
                c.execute("SELECT * FROM settings").fetchall()
        except Exception as e:  # noqa: BLE001
            print(f"db warm 异常: {e}")

    threading.Thread(target=run, name="db-warm", daemon=True).start()
