"""HTTP 客户端：UA、超时、重试、同主机限速。"""

from __future__ import annotations

import logging
import threading
import time

import httpx

from .. import config, db

log = logging.getLogger("spider.client")

_retry_status = {429, 500, 502, 503, 504}
_throttle_lock = threading.Lock()
_last_request_ts = 0.0


class SiteClient:
    """同步 httpx 客户端。线程间共享，内部做限速与重试。"""

    def __init__(self, delay: float | None = None, timeout: float = 25.0):
        if delay is None:
            delay = float(db.get_settings().get("request_delay", 0.15))
        self.delay = delay
        self._client = httpx.Client(
            headers={"User-Agent": config.UA, "Referer": config.BASE_URL + "/"},
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def get_text(self, url: str, *, retries: int = 3) -> str:
        global _last_request_ts
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            with _throttle_lock:
                wait = self.delay - (time.monotonic() - _last_request_ts)
                if wait > 0:
                    time.sleep(wait)
                _last_request_ts = time.monotonic()
            try:
                resp = self._client.get(url)
                if resp.status_code in _retry_status:
                    raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                resp.raise_for_status()
                return resp.text
            except Exception as e:  # noqa: BLE001 - 记录后重试
                last_err = e
                log.warning("GET %s 第%d次失败: %s", url, attempt, e)
                time.sleep(min(2 ** attempt, 8))
        raise ConnectionError(f"GET {url} 重试{retries}次仍失败: {last_err}")

    def get_bytes(self, url: str, *, retries: int = 3) -> bytes:
        global _last_request_ts
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                return resp.content
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning("GET(bytes) %s 第%d次失败: %s", url, attempt, e)
                time.sleep(min(2 ** attempt, 8))
        raise ConnectionError(f"GET {url} 重试{retries}次仍失败: {last_err}")
