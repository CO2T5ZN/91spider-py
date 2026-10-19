"""每日增量检查：到点扫描所有已完成任务的分类列表页，发现新视频则重启任务下载。

列表页新视频排在最前：逐页抓取并与本地 videos 表对比（video_key 去重），
某整页无新增即停；无新增的任务状态保持不变，有新增的自动置 running 下载，
下载完成后同样走自动重试/完结流程。
"""

from __future__ import annotations

import datetime
import logging
import threading

from .. import db, events
from ..scraper import parser
from ..scraper.client import SiteClient
from .manager import DownloadManager

log = logging.getLogger("spider.daily")

SCAN_MAX_PAGES = 3          # 新内容总在最前，最多扫 3 页
_loop: threading.Thread | None = None
_wakeup = threading.Event()  # 手动触发后唤醒调度线程重算下次时间


def _parse_hhmm(s: str) -> tuple[int, int]:
    hh, mm = str(s).strip().split(":")
    hh, mm = int(hh), int(mm)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"非法时间: {s}")
    return hh, mm


def _seconds_until(hh: int, mm: int) -> float:
    now = datetime.datetime.now()
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()


def run_check(manual: bool = False) -> dict:
    """扫描全部已完成任务（跳过手动队列）：有新增则启动对应任务。返回概要。"""
    client = SiteClient()
    started: list[dict] = []
    total_new = unchanged = failed = 0
    tasks = db.query_all(
        "SELECT t.id AS task_id, t.category_id, c.name, c.type, c.path "
        "FROM tasks t JOIN categories c ON c.id = t.category_id "
        "WHERE t.state='completed' ORDER BY t.id")
    for t in tasks:
        if t["type"] == "manual":
            continue  # 手动队列无列表页可枚举
        try:
            new = 0
            for page in range(1, SCAN_MAX_PAGES + 1):
                url = parser.page_url(t["path"], page)
                html = client.get_text(url)
                items = parser.parse_list_items(html, t["type"], t["path"])
                if not items:
                    break
                page_new = sum(
                    1 for it in items
                    if not db.query_one(
                        "SELECT id FROM videos WHERE category_id=? AND video_key=?",
                        (t["category_id"], it["video_key"])))
                new += page_new
                if page_new == 0:
                    break  # 整页都已入库：更深的页不会新增
            if new:
                events.publish_log("info", f"每日增量：{t['name']} 新增 {new} 个视频，开始下载")
                DownloadManager.start_task(t["task_id"], note=f"每日增量：新增 {new} 个")
                started.append({"task_id": t["task_id"], "name": t["name"], "new": new})
                total_new += new
            else:
                unchanged += 1
        except Exception as e:  # noqa: BLE001 - 单个分类失败不影响其余
            failed += 1
            log.exception("每日增量检查失败 task=%s", t["task_id"])
            events.publish_log("warn", f"每日增量检查 {t['name']} 失败: {e}")
    summary = {"checked": len(tasks), "started": started,
               "new_videos": total_new, "unchanged": unchanged, "failed": failed}
    events.publish_log(
        "info", f"每日增量检查完成：{len(started)} 个任务有更新（新增 {total_new}），"
                f"{unchanged} 个无变化" + (f"，{failed} 个检查失败" if failed else ""))
    return summary


def trigger_now() -> dict:
    """手动立即检查一次（API 调用）；同时唤醒调度线程重算下次定时。"""
    result = run_check(manual=True)
    _wakeup.set()
    return result


def _run() -> None:
    while True:
        try:
            hh, mm = _parse_hhmm(db.get_settings().get("daily_update_time", "04:00"))
        except ValueError:
            log.warning("daily_update_time 非法，回退 04:00")
            hh, mm = 4, 0
        if _wakeup.wait(timeout=_seconds_until(hh, mm)):
            _wakeup.clear()
            continue  # 手动触发过：重算下一次定时，避免紧接着重复跑
        try:
            if db.get_settings().get("daily_update", "1") == "1":
                log.info("每日增量定时检查开始")
                run_check()
        except Exception:  # noqa: BLE001
            log.exception("每日增量调度异常")


def start() -> None:
    global _loop
    if _loop and _loop.is_alive():
        return
    _loop = threading.Thread(target=_run, name="daily-update", daemon=True)
    _loop.start()
