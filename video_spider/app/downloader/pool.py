"""动态线程池：工作线程从队列取任务，支持运行中调整线程数。"""

from __future__ import annotations

import logging
import queue
import threading

log = logging.getLogger("spider.pool")

_POISON = object()


class DynamicPool:
    """size 可在运行中上调/下调的工作线程池。

    worker_fn(item) 由调用方提供，异常需自行捕获（池内兜底记录）。
    下调时多余线程在空闲检查点自行退出；stop() 用毒丸+标志位收尾。
    """

    def __init__(self, worker_fn, size: int, name: str = "pool"):
        self._worker_fn = worker_fn
        self._desired = max(1, size)
        self._name = name
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._shutdown = False
        self._counter = 0

    @property
    def size(self) -> int:
        with self._lock:
            return self._desired

    def submit(self, item) -> None:
        self._queue.put(item)

    def qsize(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        with self._lock:
            self._shutdown = False
            while len(self._threads) < self._desired:
                self._spawn_locked()

    def resize(self, size: int) -> None:
        size = max(1, size)
        with self._lock:
            self._desired = size
            while len(self._threads) < size and not self._shutdown:
                self._spawn_locked()
        log.debug("%s resized to %d", self._name, size)

    def stop(self, drain: bool = False) -> None:
        with self._lock:
            self._shutdown = True
            threads = list(self._threads)
        if drain:
            for _ in threads:
                self._queue.put(_POISON)
        else:
            # 清空队列再塞毒丸，尽快停
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            for _ in threads:
                self._queue.put(_POISON)

    def join(self, timeout: float | None = None) -> None:
        with self._lock:
            threads = list(self._threads)
        for t in threads:
            t.join(timeout=timeout)

    def _spawn_locked(self) -> None:
        self._counter += 1
        t = threading.Thread(target=self._run, name=f"{self._name}-w{self._counter}", daemon=True)
        self._threads.append(t)
        t.start()

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._shutdown:
                    self._remove_thread(threading.current_thread())
                    return
                if len(self._threads) > self._desired:
                    self._remove_thread(threading.current_thread())
                    return
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is _POISON:
                with self._lock:
                    self._remove_thread(threading.current_thread())
                return
            try:
                self._worker_fn(item)
            except Exception:  # noqa: BLE001
                log.exception("%s worker 异常", self._name)

    def _remove_thread(self, t: threading.Thread) -> None:
        try:
            self._threads.remove(t)
        except ValueError:
            pass
