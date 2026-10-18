"""SQLite 持久化：单连接 + 全局锁（WAL），含全部 DAO。"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

_CONN: sqlite3.Connection | None = None
_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,
    group_name  TEXT,
    type        TEXT NOT NULL,            -- video|search|melonshort|heiliao|av|movieset|novel|external|other
    video_count INTEGER,                  -- data-rec-total 精确总数；NULL=未知（melonshort 等）
    page_size   INTEGER,                  -- data-rec-per-page
    status      TEXT NOT NULL DEFAULT 'new',  -- new|counting|ready|no_pager|unsupported|error
    error       TEXT,
    counted_at  TEXT,
    enabled     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS videos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id    INTEGER NOT NULL REFERENCES categories(id),
    video_key      TEXT NOT NULL,
    detail_url     TEXT NOT NULL,
    title          TEXT,
    source         TEXT NOT NULL DEFAULT 'batch',    -- batch=分类任务批量 manual=浏览器插件手动提交
    cover_url      TEXT,                             -- 详情页 og:image 原始地址（CDN 有时效）
    cover_path     TEXT,                             -- 本地封面文件相对路径（data/ 下）
    tags           TEXT,                             -- 详情页 video:tag 标签，JSON 数组
    m3u8_url       TEXT,
    total_segments INTEGER,
    status         TEXT NOT NULL DEFAULT 'pending',  -- pending|downloading|done|failed
    error          TEXT,
    created_at     TEXT,
    updated_at     TEXT,
    UNIQUE(category_id, video_key)
);
CREATE INDEX IF NOT EXISTS idx_videos_cat_status ON videos(category_id, status);
CREATE TABLE IF NOT EXISTS segments (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES videos(id),
    seq      INTEGER NOT NULL,
    url      TEXT NOT NULL,
    status   TEXT NOT NULL DEFAULT 'pending',  -- pending|done
    size     INTEGER,
    UNIQUE(video_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_segments_video_status ON segments(video_id, status);
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL REFERENCES categories(id),
    thread_count INTEGER NOT NULL DEFAULT 3,
    state        TEXT NOT NULL DEFAULT 'running',  -- running|paused|stopped|completed|failed
    note         TEXT,
    created_at   TEXT,
    updated_at   TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _migrate(conn: sqlite3.Connection) -> None:
    """老库补列（ALTER TABLE 幂等）。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
    for col, ddl in [
        ("source", "TEXT NOT NULL DEFAULT 'batch'"),
        ("cover_url", "TEXT"),
        ("cover_path", "TEXT"),
        ("tags", "TEXT"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE videos ADD COLUMN {col} {ddl}")


def init() -> None:
    global _CONN
    with _LOCK:
        if _CONN is not None:
            return
        _CONN = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _CONN.execute("PRAGMA journal_mode=WAL")
        _CONN.execute("PRAGMA foreign_keys=ON")
        _CONN.executescript(SCHEMA)
        _migrate(_CONN)
        for k, v in config.DEFAULT_SETTINGS.items():
            _CONN.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
        _CONN.commit()


def execute(sql: str, params: tuple = ()) -> int:
    with _LOCK:
        cur = _CONN.execute(sql, params)
        _CONN.commit()
        return cur.lastrowid


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with _LOCK:
        return [dict(r) for r in _CONN.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    with _LOCK:
        row = _CONN.execute(sql, params).fetchone()
        return dict(row) if row else None


# ---------- settings ----------

def get_settings() -> dict:
    return {r["key"]: r["value"] for r in query_all("SELECT key, value FROM settings")}


def set_setting(key: str, value: str) -> None:
    execute("INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


# ---------- categories ----------

def upsert_category(name: str, path: str, group_name: str | None, ctype: str, enabled: bool) -> int:
    return execute(
        "INSERT INTO categories(name, path, group_name, type, enabled, updated_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(path) DO UPDATE SET name=excluded.name, group_name=excluded.group_name, "
        "type=excluded.type, enabled=excluded.enabled, updated_at=excluded.updated_at",
        (name, path, group_name, ctype, int(enabled), now()),
    )


def update_category_count(cat_id: int, video_count: int | None, page_size: int | None,
                          status: str, error: str | None = None) -> None:
    execute(
        "UPDATE categories SET video_count=?, page_size=?, status=?, error=?, counted_at=?, updated_at=? WHERE id=?",
        (video_count, page_size, status, error, now(), now(), cat_id),
    )


def set_category_status(cat_id: int, status: str, error: str | None = None) -> None:
    execute("UPDATE categories SET status=?, error=?, updated_at=? WHERE id=?",
            (status, error, now(), cat_id))


def list_categories() -> list[dict]:
    return query_all("SELECT * FROM categories ORDER BY group_name, id")


def get_category(cat_id: int) -> dict | None:
    return query_one("SELECT * FROM categories WHERE id=?", (cat_id,))


def countable_categories() -> list[dict]:
    """需要抓首页计数的分类：可下载类型 且 尚未有精确计数。"""
    return query_all(
        "SELECT * FROM categories WHERE enabled=1 AND type IN "
        "('video','search','melonshort','heiliao','av') AND status NOT IN ('ready','no_pager')"
    )


# ---------- videos ----------

def insert_video_if_missing(category_id: int, video_key: str, detail_url: str,
                            title: str | None, source: str = "batch") -> int:
    row = query_one("SELECT id FROM videos WHERE category_id=? AND video_key=?", (category_id, video_key))
    if row:
        return row["id"]
    return execute(
        "INSERT INTO videos(category_id, video_key, detail_url, title, source, status, created_at, updated_at) "
        "VALUES(?,?,?,?,?, 'pending', ?, ?)",
        (category_id, video_key, detail_url, title, source, now(), now()),
    )


def claim_next_pending_video(category_id: int) -> dict | None:
    """原子认领一个 pending 视频（ downloading=进行中，供断点恢复）。"""
    with _LOCK:
        row = query_one(
            "SELECT * FROM videos WHERE category_id=? AND status IN ('pending','downloading') ORDER BY id LIMIT 1",
            (category_id,),
        )
        if not row:
            return None
        execute("UPDATE videos SET status='downloading', error=NULL, updated_at=? WHERE id=?",
                (now(), row["id"]))
        row["status"] = "downloading"
        return row


def claim_video_by_id(video_id: int) -> bool:
    """CAS 认领指定视频：pending/downloading -> downloading；其余状态跳过。"""
    with _LOCK:
        row = query_one("SELECT status FROM videos WHERE id=?", (video_id,))
        if not row or row["status"] not in ("pending", "downloading"):
            return False
        execute("UPDATE videos SET status='downloading', error=NULL, updated_at=? WHERE id=?",
                (now(), video_id))
        return True


def update_video(video_id: int, **fields) -> None:
    allowed = ("title", "m3u8_url", "total_segments", "status", "error",
               "cover_url", "cover_path", "tags", "source")
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return
    sets.append("updated_at=?")
    params.extend([now(), video_id])
    execute(f"UPDATE videos SET {', '.join(sets)} WHERE id=?", tuple(params))


def list_videos(category_id: int, status: str | None = None, limit: int = 200, offset: int = 0) -> list[dict]:
    if status:
        return query_all(
            "SELECT * FROM videos WHERE category_id=? AND status=? ORDER BY id LIMIT ? OFFSET ?",
            (category_id, status, limit, offset),
        )
    return query_all("SELECT * FROM videos WHERE category_id=? ORDER BY id LIMIT ? OFFSET ?",
                     (category_id, limit, offset))


def video_status_summary(category_id: int) -> dict:
    rows = query_all(
        "SELECT status, COUNT(*) AS n FROM videos WHERE category_id=? GROUP BY status", (category_id,)
    )
    summary = {r["status"]: r["n"] for r in rows}
    total = sum(summary.values())
    done = summary.get("done", 0)
    failed = summary.get("failed", 0)
    return {"total": total, "done": done, "failed": failed,
            "pending": summary.get("pending", 0), "downloading": summary.get("downloading", 0)}


def reset_downloading_videos(category_id: int) -> int:
    """启动恢复：进行中的视频退回队列（分片状态不动，续传用）。返回退回数量。"""
    with _LOCK:
        n = _CONN.execute(
            "SELECT COUNT(*) FROM videos WHERE category_id=? AND status='downloading'",
            (category_id,)).fetchone()[0]
        if n:
            execute("UPDATE videos SET status='pending', updated_at=? WHERE category_id=? AND status='downloading'",
                    (now(), category_id))
        return n


# ---------- segments ----------

def replace_segments(video_id: int, seq_urls: list[tuple[int, str]]) -> None:
    """重建分片清单；已完成的分片保留（断点续传）。"""
    with _LOCK:
        keep = {r["seq"]: r["id"] for r in query_all(
            "SELECT id, seq FROM segments WHERE video_id=? AND status='done'", (video_id,))}
        execute("DELETE FROM segments WHERE video_id=?", (video_id,))
        for seq, url in seq_urls:
            if seq in keep:
                execute("INSERT INTO segments(video_id, seq, url, status) VALUES(?,?,?, 'done')",
                        (video_id, seq, url))
            else:
                execute("INSERT INTO segments(video_id, seq, url) VALUES(?,?,?)", (video_id, seq, url))


def next_pending_segment(video_id: int) -> dict | None:
    return query_one(
        "SELECT * FROM segments WHERE video_id=? AND status='pending' ORDER BY seq LIMIT 1", (video_id,)
    )


def mark_segment_done(seg_id: int, size: int) -> None:
    execute("UPDATE segments SET status='done', size=? WHERE id=?", (size, seg_id))


def segment_summary(video_id: int) -> dict:
    rows = query_all("SELECT status, COUNT(*) AS n FROM segments WHERE video_id=? GROUP BY status", (video_id,))
    d = {r["status"]: r["n"] for r in rows}
    done, total = d.get("done", 0), sum(d.values())
    return {"done": done, "total": total}


# ---------- tasks ----------

def create_task(category_id: int, thread_count: int) -> int:
    return execute(
        "INSERT INTO tasks(category_id, thread_count, state, created_at, updated_at) VALUES(?,?,?,?,?)",
        (category_id, thread_count, "running", now(), now()),
    )


def list_tasks() -> list[dict]:
    tasks = query_all("SELECT * FROM tasks ORDER BY id DESC")
    for t in tasks:
        t["progress"] = video_status_summary(t["category_id"])
    return tasks


def get_task(task_id: int) -> dict | None:
    row = query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if row:
        row["progress"] = video_status_summary(row["category_id"])
    return row


def update_task(task_id: int, state: str | None = None, thread_count: int | None = None, note: str | None = None) -> None:
    sets, params = ["updated_at=?"], [now()]
    if state is not None:
        sets.append("state=?"); params.append(state)
    if thread_count is not None:
        sets.append("thread_count=?"); params.append(thread_count)
    if note is not None:
        sets.append("note=?"); params.append(note)
    params.append(task_id)
    execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", tuple(params))


def running_tasks() -> list[dict]:
    return query_all("SELECT * FROM tasks WHERE state IN ('running','paused') ORDER BY id")


def recover_on_startup() -> None:
    """把上次运行遗留的任务置为 paused，进行中视频退回队列（分片保留，可续传）。"""
    ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    for t in running_tasks():
        rolled_back = reset_downloading_videos(t["category_id"])
        if t["state"] == "paused":
            note = f"服务重启（{ts}），任务此前已暂停，状态未变"
        elif rolled_back:
            note = f"服务重启（{ts}），已自动暂停；{rolled_back} 个进行中视频已退回队列，可继续"
        else:
            note = f"服务重启（{ts}），已自动暂停，可继续"
        update_task(t["id"], state="paused", note=note)


def task_snapshot(task_id: int) -> dict:
    t = get_task(task_id)
    return {"event": "task", "task": t} if t else {}


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
