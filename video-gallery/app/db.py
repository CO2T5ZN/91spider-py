"""只读数据库访问：与 video_spider 共用数据，但读的是**本地 SSD 上的定期快照**。

数据盘（机械盘）与下载写入共用，繁忙时任何一次冷读都可能卡数秒，因此：
- 后台每 60s 用 SQLite backup API 把源库快照到本地盘（临时文件 + 原子替换）；
- 查询全部走快照上的单一共享连接（全局锁串行 + 32MB 页缓存），查询零机械盘 I/O；
- 快照刷新后重开连接，数据延迟 ≤ 刷新间隔，对展示站无感。
源库尚无快照时（启动头几秒）直接读源库兜底。
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

# settings 变化极少，短 TTL 缓存，省掉每条视频路径解析时的重复查询
_settings_cache: dict = {"t": 0.0, "v": {}}
_SETTINGS_TTL = 5.0

_SNAPSHOT_INTERVAL = 60.0


def snapshot_path() -> Path:
    return Path(os.environ.get("GALLERY_DB_CACHE",
                               config.PROJECT_ROOT / ".db-cache")) / "spider.db"


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size=-32000")   # 32MB 页缓存
    conn.execute("PRAGMA mmap_size=134217728")  # 读页零拷贝
    return conn


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        snap = snapshot_path()
        if snap.is_file() and snap.stat().st_size > 0:
            _conn = _open(snap)
        else:
            _conn = _open(config.DB_PATH)  # 兜底：快照未就绪时直读源库
    return _conn


def _refresh_snapshot() -> None:
    """从源库做在线快照（临时文件 + 原子替换），成功后重开共享连接。"""
    snap_dir = snapshot_path().parent
    snap_dir.mkdir(parents=True, exist_ok=True)
    dst = snap_dir / "spider.db"
    tmp = snap_dir / "spider.db.tmp"
    src = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True, timeout=15)
    try:
        dst_conn = sqlite3.connect(str(tmp))
        with dst_conn:
            src.backup(dst_conn)
        dst_conn.close()
        global _conn
        with _lock:
            if _conn is not None:
                _conn.close()
                _conn = None  # 先松手：Windows 下无法 os.replace 替换仍被打开的库文件（Linux 无此限制）
        os.replace(str(tmp), str(dst))
    finally:
        src.close()


def _snapshot_loop() -> None:
    while True:
        try:
            _refresh_snapshot()
        except Exception as e:  # noqa: BLE001
            print(f"db snapshot 异常: {e}")
        time.sleep(_SNAPSHOT_INTERVAL)


def start_snapshot() -> None:
    threading.Thread(target=_snapshot_loop, name="db-snapshot", daemon=True).start()


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
    """启动后台预热：把快照库整表读一遍，将页拉进连接缓存（本地盘，秒级完成）。"""

    def run():
        time.sleep(2.0)  # 等首个快照生成
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
