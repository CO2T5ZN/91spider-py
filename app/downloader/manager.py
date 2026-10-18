"""任务管理器：任务生命周期、列表枚举、视频下载流水线、断点续传、SSE 进度。

流水线（每任务）：
  枚举线程: 分类列表页 1..N → videos 表去重入库(pending) → 逐个投递给线程池
  工作线程: 认领视频 → 抓详情页 → 提取 m3u8（本期桩位，见 parser.extract_m3u8_url）
           → 解析分片清单入 segments 表 → 逐分片下载到临时目录（已完成的跳过=断点续传）
           → 全部分片完成后二进制合并为单文件 → 清理分片

暂停/停止：停止投递+线程退出；恢复时重新枚举并只认领 pending/downloading 的视频。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .. import config, db, events
from ..scraper import parser
from ..scraper.client import SiteClient
from . import m3u8
from .pool import DynamicPool

log = logging.getLogger("spider.manager")


class TaskRuntime:
    def __init__(self, task_id: int, category_id: int, thread_count: int):
        self.task_id = task_id
        self.category_id = category_id
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.enum_done = threading.Event()
        self.client = SiteClient()
        self.pool = DynamicPool(self._worker, thread_count, name=f"task{task_id}")
        self.enum_thread: threading.Thread | None = None

    def _worker(self, video_id: int) -> None:
        if self.stop_event.is_set():
            return
        try:
            DownloadManager.process_video(self, video_id)
        finally:
            events.publish("task", {"task": db.get_task(self.task_id)})
            self._maybe_complete()

    def _maybe_complete(self) -> None:
        if self.stop_event.is_set() or not self.enum_done.is_set():
            return
        p = db.video_status_summary(self.category_id)
        if p["total"] > 0 and p["pending"] == 0 and p["downloading"] == 0:
            db.update_task(self.task_id, state="completed")
            events.publish_log("info", f"任务 #{self.task_id} 全部完成")
            events.publish("task", {"task": db.get_task(self.task_id)})


class DownloadManager:
    _runtimes: dict[int, TaskRuntime] = {}
    _lock = threading.Lock()
    _client: SiteClient | None = None

    @classmethod
    def shared_client(cls) -> SiteClient:
        # 详情页/分片下载共用一个限速客户端
        if cls._client is None:
            cls._client = SiteClient()
        return cls._client

    # ---------------- 生命周期 ----------------

    @classmethod
    def recover(cls) -> None:
        db.recover_on_startup()

    @classmethod
    def create_task(cls, category_id: int, thread_count: int) -> dict:
        cat = db.get_category(category_id)
        if not cat:
            raise ValueError("分类不存在")
        if not cat["enabled"]:
            raise ValueError(f"该分类类型({cat['type']})不支持下载")
        existing = db.query_one("SELECT id FROM tasks WHERE category_id=? ORDER BY id DESC LIMIT 1",
                                (category_id,))
        if existing:
            raise ValueError(f"该分类已创建过任务 #{existing['id']}，请在下载任务页使用其继续/重试操作")
        task_id = db.create_task(category_id, thread_count)
        cls.start_task(task_id)
        return db.get_task(task_id)

    @classmethod
    def start_task(cls, task_id: int) -> None:
        task = db.get_task(task_id)
        if not task:
            raise ValueError("任务不存在")
        with cls._lock:
            rt = cls._runtimes.get(task_id)
            if rt and rt.pool and not rt.stop_event.is_set():
                return  # 已在运行
            rt = TaskRuntime(task_id, task["category_id"], task["thread_count"])
            cls._runtimes[task_id] = rt
        db.update_task(task_id, state="running", note=None)
        rt.enum_thread = threading.Thread(
            target=cls._enumerate, args=(rt,), name=f"task{task_id}-enum", daemon=True)
        rt.enum_thread.start()
        rt.pool.start()
        events.publish("task", {"task": db.get_task(task_id)})
        events.publish_log("info", f"任务 #{task_id} 启动（{task['thread_count']} 线程）")

    @classmethod
    def pause_task(cls, task_id: int) -> None:
        cls._halt(task_id, state="paused", note="已暂停，可继续")

    @classmethod
    def stop_task(cls, task_id: int) -> None:
        cls._halt(task_id, state="stopped", note="已停止")

    @classmethod
    def _halt(cls, task_id: int, state: str, note: str) -> None:
        with cls._lock:
            rt = cls._runtimes.pop(task_id, None)
        if rt:
            rt.stop_event.set()
            rt.pool.stop()
        db.update_task(task_id, state=state, note=note)
        db.reset_downloading_videos(db.get_task(task_id)["category_id"])
        events.publish("task", {"task": db.get_task(task_id)})

    @classmethod
    def resize_task(cls, task_id: int, thread_count: int) -> None:
        with cls._lock:
            rt = cls._runtimes.get(task_id)
        if rt and not rt.stop_event.is_set():
            rt.pool.resize(thread_count)
        db.update_task(task_id, thread_count=thread_count)
        events.publish("task", {"task": db.get_task(task_id)})

    @classmethod
    def retry_failed(cls, task_id: int) -> None:
        task = db.get_task(task_id)
        if not task:
            raise ValueError("任务不存在")
        category_id = task["category_id"]
        reset_ids = [r["id"] for r in db.query_all(
            "SELECT id FROM videos WHERE category_id=? AND status='failed'", (category_id,))]
        db.execute("UPDATE videos SET status='pending', error=NULL, updated_at=? "
                   "WHERE category_id=? AND status='failed'", (db.now(), category_id))
        for vid in reset_ids:
            publish_video_event(category_id, vid)
        if task["state"] in ("completed", "stopped"):
            db.update_task(task_id, state="paused", note="失败项已重置，点击继续重跑")
        events.publish("task", {"task": db.get_task(task_id)})

    # ---------------- 枚举 ----------------

    @classmethod
    def _enumerate(cls, rt: TaskRuntime) -> None:
        cat = db.get_category(rt.category_id)
        if cat["type"] == "manual":
            # 插件队列：无列表页可枚举，直接投递所有待处理视频（重启后恢复队列）
            for r in db.query_all(
                    "SELECT id FROM videos WHERE category_id=? AND status IN ('pending','downloading') "
                    "ORDER BY id", (cat["id"],)):
                rt.pool.submit(r["id"])
            rt.enum_done.set()
            return
        settings = db.get_settings()
        max_pages = int(settings.get("max_list_pages", "50"))
        try:
            for page in range(1, max_pages + 1):
                if rt.stop_event.is_set():
                    return
                url = parser.page_url(cat["path"], page)
                html = rt.client.get_text(url)
                items = parser.parse_list_items(html, cat["type"], cat["path"])
                if not items:
                    break
                batch, new_count = [], 0
                for it in items:
                    row = db.query_one("SELECT id FROM videos WHERE category_id=? AND video_key=?",
                                       (rt.category_id, it["video_key"]))
                    if row:
                        vid = row["id"]
                    else:
                        vid = db.insert_video_if_missing(rt.category_id, it["video_key"],
                                                         it["detail_url"], it["title"])
                        new_count += 1
                    if vid not in batch:
                        batch.append(vid)
                for vid in batch:
                    rt.pool.submit(vid)
                events.publish_log("debug", f"任务 #{rt.task_id} 列表第{page}页: {len(items)} 条 "
                                            f"(新增 {new_count})，本页下载完成后继续翻页")
                cls._wait_batch_done(rt, batch)
                if new_count == 0 and not _category_has_pending(rt.category_id):
                    break  # 本页无新视频且无遗留待处理 → 内容到底（或 AJAX 重复页）
            return
        except Exception as e:  # noqa: BLE001
            log.exception("枚举失败 task=%s", rt.task_id)
            events.publish_log("warn", f"任务 #{rt.task_id} 列表枚举中断: {e}")
        finally:
            rt.enum_done.set()
            # 兜底完成判定：最后一次视频完成时枚举线程可能还在抓下一页，
            # 错过 worker 侧的完成检查；此处队列已无待处理则直接收尾
            if not rt.stop_event.is_set():
                p = db.video_status_summary(rt.category_id)
                if p["total"] > 0 and p["pending"] == 0 and p["downloading"] == 0:
                    db.update_task(rt.task_id, state="completed")
                    events.publish("task", {"task": db.get_task(rt.task_id)})

    @classmethod
    def _wait_batch_done(cls, rt: TaskRuntime, batch: list[int]) -> None:
        """等待本页投递的视频全部到达终态（done/failed）后再返回。"""
        if not batch:
            return
        placeholders = ",".join("?" * len(batch))
        while not rt.stop_event.is_set():
            row = db.query_one(
                f"SELECT COUNT(*) AS n FROM videos WHERE id IN ({placeholders}) "
                "AND status IN ('pending','downloading')", tuple(batch))
            if not row or row["n"] == 0:
                return
            time.sleep(0.5)

    # ---------------- 单视频流水线 ----------------

    @classmethod
    def process_video(cls, rt: TaskRuntime, video_id: int) -> None:
        video = db.query_one("SELECT * FROM videos WHERE id=?", (video_id,))
        if not video or video["status"] == "done":
            return
        if not db.claim_video_by_id(video_id):
            return  # 已被认领或不可下载

        def emit():
            publish_video_event(rt.category_id, video_id)

        try:
            emit()
            html = rt.client.get_text(video["detail_url"])
            # 元数据：真实标题（修正列表页脏标题）+ 封面 + 标签
            meta = parser.extract_detail_meta(html)
            updates = {}
            if meta["title"] and not parser.is_clean_title(video["title"]):
                updates["title"] = meta["title"]
                video["title"] = meta["title"]
            if meta["cover_url"]:
                updates["cover_url"] = meta["cover_url"]
            if meta["tags"]:
                updates["tags"] = json.dumps(meta["tags"], ensure_ascii=False)
            if updates:
                db.update_video(video_id, **updates)
            m3u8_url = parser.extract_m3u8_url(html, video["detail_url"], rt.client)
            if not m3u8_url:
                db.update_video(video_id, status="failed",
                                error="未能从详情页解析出 m3u8（detail_play 流程失败）")
                emit()
                return

            playlist = cls._resolve_playlist(rt.client, m3u8_url)
            segs = [(s.seq, s.url) for s in playlist.segments]
            db.replace_segments(video_id, segs)
            db.update_video(video_id, m3u8_url=m3u8_url, total_segments=len(segs))
            emit()

            # AES-128：拉取密钥（playlist 级一次）
            key, pl_iv = None, playlist
            if playlist.key_url:
                key = rt.client.get_bytes(playlist.key_url)
                if len(key) != 16:
                    raise m3u8.M3u8Error(f"AES key 长度异常: {len(key)}")

            seg_dir = Path(config.TMP_DIR) / str(video["video_key"])
            init_file = None
            if playlist.map_url:
                init_file = seg_dir / "init.mp4"
                if not init_file.exists():
                    init_file.write_bytes(rt.client.get_bytes(playlist.map_url))
            cls._download_segments(rt, video_id, seg_dir, key, pl_iv)

            p = db.segment_summary(video_id)
            if p["total"] and p["done"] < p["total"]:
                emit()  # 中途暂停，保留现场
                return

            root = choose_video_root()
            out_dir = root / _safe_name(_category_name(rt.category_id))
            out_file = out_dir / f"{video['video_key']}.ts"
            m3u8.merge_segments(seg_dir, out_file, p["total"], init_file)
            if db.get_settings().get("output_format", "mp4") == "mp4":
                mp4 = _remux_to_mp4(out_file)
                if mp4:
                    out_file.unlink()
                    out_file = mp4
            db.update_video(video_id, status="done", error=None)
            cover_rel = _generate_cover(out_file, video["video_key"])
            if cover_rel:
                db.update_video(video_id, cover_path=cover_rel)
            if db.get_settings().get("keep_segments") != "1":
                shutil.rmtree(seg_dir, ignore_errors=True)
            emit()
            events.publish_log("info", f"视频 {video['video_key']} 完成 -> {out_file}")
        except m3u8.UnsupportedEncryption as e:
            db.update_video(video_id, status="failed", error=str(e))
            emit()
        except Exception as e:  # noqa: BLE001
            log.exception("视频处理失败 %s", video["video_key"])
            db.update_video(video_id, status="failed", error=str(e)[:300])
            emit()

    @classmethod
    def _resolve_playlist(cls, client: SiteClient, url: str, depth: int = 0) -> m3u8.Playlist:
        if depth > 3:
            raise m3u8.M3u8Error("m3u8 嵌套过深")
        text = client.get_text(url)
        pl = m3u8.parse(text, url)
        if pl.is_master:
            return cls._resolve_playlist(client, pl.variant_url, depth + 1)
        return pl

    @classmethod
    def _download_segments(cls, rt: TaskRuntime, video_id: int, seg_dir: Path,
                           key: bytes | None, playlist) -> None:
        seg_dir.mkdir(parents=True, exist_ok=True)
        while not rt.stop_event.is_set():
            seg = db.next_pending_segment(video_id)
            if not seg:
                return
            data = rt.client.get_bytes(seg["url"])
            if key is not None:
                data = m3u8.decrypt_segment(data, key, m3u8.segment_iv(playlist, seg["seq"]))
            f = seg_dir / f"seg_{seg['seq']:05d}.ts"
            tmp = f.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(f)
            db.mark_segment_done(seg["id"], len(data))
            publish_video_event(rt.category_id, video_id)


def publish_video_event(category_id: int, video_id: int) -> None:
    """发布视频事件：始终读取数据库当前行，保证字段（标题/状态/错误）完整准确。"""
    row = db.query_one("SELECT id, video_key, title, status, error FROM videos WHERE id=?", (video_id,))
    if not row:
        return
    seg = db.segment_summary(video_id)
    events.publish("video", {"id": row["id"], "category_id": category_id,
                             "video_key": row["video_key"], "title": row["title"],
                             "status": row["status"], "error": row["error"],
                             "done_segments": seg["done"],
                             "total_segments": seg["total"]})


# ---------------- 浏览器插件：手动提交队列（固定单线程） ----------------

MANUAL_CATEGORY_PATH = "manual://plugin"
MANUAL_CATEGORY_NAME = "手动提交"

_MANUAL_KEY_PATTERNS = [
    re.compile(r"/comic/index/detail\?video_key=(\d+)"),
    re.compile(r"/comic/index/avdetail\?video_key=(\w+)"),
    re.compile(r"/melonshort/video/(\d+)"),
    re.compile(r"/heiliao-chigua/(\w+)"),
]


def extract_manual_key(detail_url: str) -> str:
    for pat in _MANUAL_KEY_PATTERNS:
        m = pat.search(detail_url)
        if m:
            return m.group(1)
    raise ValueError("无法识别的视频详情页 URL")


def _ensure_manual_category() -> int:
    row = db.query_one("SELECT id FROM categories WHERE path=?", (MANUAL_CATEGORY_PATH,))
    if row:
        return row["id"]
    return db.upsert_category(MANUAL_CATEGORY_NAME, MANUAL_CATEGORY_PATH, "浏览器插件",
                              "manual", enabled=0)


def _ensure_manual_task(category_id: int) -> int:
    task = db.query_one("SELECT id FROM tasks WHERE category_id=? ORDER BY id DESC LIMIT 1",
                        (category_id,))
    if task:
        return task["id"]
    return db.create_task(category_id, thread_count=1)  # 固定单线程


def delete_task(task_id: int) -> None:
    """删除已停止的任务及其视频/分片记录（分类本身保留）。"""
    task = db.get_task(task_id)
    if not task:
        return
    DownloadManager.stop_task(task_id)  # 兜底停掉运行时
    category_id = task["category_id"]
    db.execute("DELETE FROM segments WHERE video_id IN "
               "(SELECT id FROM videos WHERE category_id=?)", (category_id,))
    db.execute("DELETE FROM videos WHERE category_id=?", (category_id,))
    db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    events.publish("task", {"task": None, "deleted": task_id})


def submit_manual(detail_url: str, title: str | None = None) -> dict:
    """插件提交：幂等。已下载/排队中的直接返回现状，失败的可重新提交。"""
    key = extract_manual_key(detail_url)
    cat_id = _ensure_manual_category()
    task_id = _ensure_manual_task(cat_id)
    vid = db.insert_video_if_missing(cat_id, key, detail_url, title, source="manual")
    status = db.query_one("SELECT status FROM videos WHERE id=?", (vid,))["status"]
    action = {"pending": "already_queued", "downloading": "already_downloading",
              "done": "already_done", "failed": "resubmitted"}[status]
    if status == "failed":
        db.update_video(vid, status="pending", error=None)
    DownloadManager.start_task(task_id)  # 幂等：运行中无副作用
    with DownloadManager._lock:
        rt = DownloadManager._runtimes.get(task_id)
    if rt and not rt.stop_event.is_set():
        rt.pool.submit(vid)
    current = db.query_one("SELECT status FROM videos WHERE id=?", (vid,))["status"]
    events.publish("task", {"task": db.get_task(task_id)})
    return {"action": action, "video_id": vid, "task_id": task_id, "status": current}


def manual_state(detail_url: str) -> dict:
    """插件轮询：当前页视频状态 + 队列概况。"""
    empty = {"video": None, "downloading_count": 0, "queue_count": 0, "active": None}
    try:
        key = extract_manual_key(detail_url)
    except ValueError:
        return empty
    cat = db.query_one("SELECT id FROM categories WHERE path=?", (MANUAL_CATEGORY_PATH,))
    if not cat:
        return empty
    video = db.query_one(
        "SELECT id, status, title, error FROM videos WHERE category_id=? AND video_key=?",
        (cat["id"], key))
    downloading = db.query_one(
        "SELECT COUNT(*) AS n FROM videos WHERE category_id=? AND status='downloading'",
        (cat["id"],))["n"]
    queue = db.query_one(
        "SELECT COUNT(*) AS n FROM videos WHERE category_id=? AND status='pending'",
        (cat["id"],))["n"]
    active = None
    if downloading:
        av = db.query_one(
            "SELECT id FROM videos WHERE category_id=? AND status='downloading' ORDER BY id LIMIT 1",
            (cat["id"],))
        if av:
            aseg = db.segment_summary(av["id"])
            active = {"id": av["id"], "done_segments": aseg["done"],
                      "total_segments": aseg["total"]}
    vinfo = None
    if video:
        seg = db.segment_summary(video["id"])
        vinfo = {"id": video["id"], "status": video["status"], "title": video["title"],
                 "error": video["error"], "done_segments": seg["done"],
                 "total_segments": seg["total"]}
    return {"video": vinfo, "downloading_count": downloading,
            "queue_count": queue, "active": active}


def _category_name(category_id: int) -> str:
    cat = db.get_category(category_id)
    return cat["name"] if cat else "unknown"


def video_roots() -> list[Path]:
    """所有候选视频保存根目录（多硬盘支持）。

    优先级：settings.video_dirs（每行/分号一个）> 旧 settings.video_dir > 默认 VIDEO_DIR。
    每个视频完成时实时读取，增删保存位置后无需重启。
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
    roots.append(Path(config.VIDEO_DIR))
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


MIN_FREE_BYTES = 5 * 1024**3  # 候选盘剩余空间低于此值时降级为最后选择


def choose_video_root() -> Path:
    """为本次保存选盘：可写候选中剩余空间最大者（多硬盘）。

    移动硬盘可能未挂载/已拔出：目录建不了或写测试失败即跳过该候选；
    所有盘剩余都不足 5GB 时仍选剩余最大的一块（避免任务直接失败）。
    """
    candidates: list[tuple[int, Path]] = []
    for root in video_roots():
        try:
            root.mkdir(parents=True, exist_ok=True)
            probe = root / ".write-test"
            probe.write_bytes(b"")
            probe.unlink(missing_ok=True)
            free = shutil.disk_usage(root).free
        except OSError as e:
            log.warning("保存目录不可用，跳过：%s（%s）", root, e)
            continue
        candidates.append((free, root))
    if candidates:
        candidates.sort(reverse=True)
        free, root = candidates[0]
        if free < MIN_FREE_BYTES:
            log.warning("所有保存目录剩余空间均不足 5GB，仍使用剩余最大的：%s", root)
        return root
    fallback = Path(config.VIDEO_DIR)
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _remux_to_mp4(ts_file: Path) -> Path | None:
    """TS 转封装为 MP4（-c copy 不重编码，仅改封装格式）；失败返回 None 并保留 ts。"""
    mp4 = ts_file.with_suffix(".mp4")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(ts_file),
             "-c", "copy", "-movflags", "+faststart", str(mp4)],
            capture_output=True, timeout=1800)
    except FileNotFoundError:
        log.warning("未找到 ffmpeg，保留 TS：%s（安装 ffmpeg 后新视频自动转 MP4）", ts_file.name)
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("ffmpeg 转封装异常 %s: %s", ts_file.name, e)
        return None
    if r.returncode == 0 and mp4.exists():
        return mp4
    mp4.unlink(missing_ok=True)
    log.warning("ffmpeg 转封装失败 %s: %s", ts_file.name,
                r.stderr.decode("utf-8", "replace")[:200])
    return None


def _generate_cover(video_file: Path, video_key: str) -> str | None:
    """从成片抽帧生成封面 covers/<video_key>.jpg（5s 处，取不到回退首帧）；失败返回 None。"""
    rel = f"covers/{video_key}.jpg"
    path = Path(config.DATA_DIR) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    for ss in ("00:00:05", "0"):
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", ss, "-i", str(video_file),
                 "-frames:v", "1", "-q:v", "3", str(path)],
                capture_output=True, timeout=120)
        except FileNotFoundError:
            log.warning("未找到 ffmpeg，跳过封面生成：%s", video_key)
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("封面抽帧异常 %s: %s", video_key, e)
            return None
        if r.returncode == 0 and path.exists() and path.stat().st_size > 1000:
            return rel
        path.unlink(missing_ok=True)
    log.warning("封面抽帧失败：%s", video_key)
    return None


def _category_has_pending(category_id: int) -> bool:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM videos WHERE category_id=? AND status IN ('pending','downloading')",
        (category_id,))
    return bool(row and row["n"])


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "unknown"


# ---------------- 模块级门面（供 API 调用） ----------------

def recover() -> None:
    DownloadManager.recover()


def create_task(category_id: int, thread_count: int) -> dict:
    return DownloadManager.create_task(category_id, thread_count)


def start_task(task_id: int) -> None:
    DownloadManager.start_task(task_id)


def pause_task(task_id: int) -> None:
    DownloadManager.pause_task(task_id)


def stop_task(task_id: int) -> None:
    DownloadManager.stop_task(task_id)


def resize_task(task_id: int, thread_count: int) -> None:
    DownloadManager.resize_task(task_id, thread_count)


def retry_failed(task_id: int) -> None:
    DownloadManager.retry_failed(task_id)
