"""分类同步：抓首页提取分类，逐分类抓第 1 页取 pager 精确计数。"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .. import config, db, events
from . import parser
from .client import SiteClient

log = logging.getLogger("spider.sync")

_sync_lock = threading.Lock()
_syncing = threading.Event()


def is_syncing() -> bool:
    return _syncing.is_set()


def run_sync(with_counts: bool = True) -> None:
    """同步入口（阻塞执行，建议由 API 侧开线程调用）。"""
    if not _sync_lock.acquire(blocking=False):
        events.publish_log("warn", "分类同步已在进行中，忽略本次请求")
        return
    _syncing.set()
    try:
        _do_sync(with_counts)
    except Exception as e:  # noqa: BLE001
        log.exception("分类同步异常")
        events.publish("sync", {"phase": "error", "message": str(e)})
    finally:
        _syncing.clear()
        _sync_lock.release()


def _do_sync(with_counts: bool) -> None:
    client = SiteClient()
    try:
        html = client.get_text(config.BASE_URL + "/")
        cats = parser.parse_home_categories(html)
        if not cats:
            events.publish("sync", {"phase": "error", "message": "首页未解析到任何 video-sub-item 分类"})
            return
        for c in cats:
            cat_id = db.upsert_category(c["name"], c["path"], c["group"], c["type"], c["enabled"])
            c["id"] = cat_id
        events.publish_log("info", f"首页解析到 {len(cats)} 个分类入口")
        events.publish("sync", {"phase": "names", "total": len(cats)})

        if not with_counts:
            events.publish("sync", {"phase": "done", "total": len(cats), "counted": 0})
            return

        targets = [c for c in cats if c["enabled"]]
        done = failed = 0
        events.publish("sync", {"phase": "start", "total": len(targets)})

        with ThreadPoolExecutor(max_workers=int(db.get_settings().get("sync_workers", "4"))) as pool:
            futures = {pool.submit(_count_one, client, c): c for c in targets}
            for fut in as_completed(futures):
                c, ok = fut.result()
                done += 1
                failed += 0 if ok else 1
                row = db.get_category(c["id"])
                events.publish("categories", {"category": row})
                events.publish("sync", {"phase": "progress", "done": done, "total": len(targets),
                                        "name": c["name"], "ok": ok})
        events.publish("sync", {"phase": "done", "total": len(targets), "counted": done - failed,
                                "failed": failed})
        events.publish_log("info", f"分类同步完成：{done - failed} 成功 / {failed} 失败")
    finally:
        client.close()


def _count_one(client: SiteClient, cat: dict) -> tuple[dict, bool]:
    """抓分类第 1 页，解析 pager 计数。"""
    try:
        db.set_category_status(cat["id"], "counting")
        html = client.get_text(parser.page_url(cat["path"], 1))
        pager = parser.parse_pager(html)
        if pager and pager["rec_total"] is not None:
            db.update_category_count(cat["id"], pager["rec_total"], pager["rec_per_page"], "ready")
        else:
            # melonshort 等 AJAX 列表页：无静态 pager，计数留空待逆向
            db.update_category_count(cat["id"], None, None, "no_pager",
                                     "列表为 AJAX 加载，暂无静态分页数据")
        return cat, True
    except Exception as e:  # noqa: BLE001
        log.warning("分类计数失败 %s: %s", cat["path"], e)
        db.set_category_status(cat["id"], "error", str(e)[:300])
        return cat, False
