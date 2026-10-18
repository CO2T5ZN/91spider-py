"""SSE 事件中心：工作线程发布事件 → asyncio 队列 → /api/events 推流。"""

from __future__ import annotations

import asyncio
import json
import logging
import threading

log = logging.getLogger("spider.events")

_loop: asyncio.AbstractEventLoop | None = None
_subscribers: set[asyncio.Queue] = set()
_sub_lock = threading.Lock()


def init(loop: asyncio.AbstractEventLoop) -> None:
    """在 FastAPI startup 中调用，捕获主事件循环。"""
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    with _sub_lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _sub_lock:
        _subscribers.discard(q)


def publish(event_type: str, payload: dict) -> None:
    """任意线程可调用。EventSource 前端按 event 名分发。"""
    msg = {"event": event_type, "data": payload}
    if _loop is None or _loop.is_closed():
        return
    with _sub_lock:
        targets = list(_subscribers)
    for q in targets:
        def _put(q=q, msg=msg):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # 慢客户端直接丢事件，靠 REST 快照兜底
        try:
            _loop.call_soon_threadsafe(_put)
        except RuntimeError:
            pass


def publish_log(level: str, message: str) -> None:
    log.info("%s: %s", level, message)
    publish("log", {"level": level, "message": message, "ts": threading.current_thread().name})


def format_sse(msg: dict) -> str:
    return f"event: {msg['event']}\ndata: {json.dumps(msg['data'], ensure_ascii=False)}\n\n"
