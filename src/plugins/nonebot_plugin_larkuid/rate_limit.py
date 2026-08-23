import asyncio
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Depends, HTTPException, Request, status


class SlidingWindowRateLimiter:
    """进程内滑动窗口限流器。

    以 `(key -> 命中时间戳队列)` 维护窗口内的请求记录，超出配额抛 429。
    仅进程内生效：多 worker 部署时每个进程各自计数，实际放行量约为配置值 × worker 数，
    对「抬高爆破成本」的定位足够；如需精确全局限流应引入共享存储。

    后台清理协程周期性淘汰空队列，避免 key 无上限累积。
    """

    def __init__(self, times: int, window_seconds: float, cleanup_interval_seconds: float = 600.0) -> None:
        self.times = times
        self.window_seconds = window_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    def _evict_queue(self, queue: deque[float], now: float) -> deque[float]:
        boundary = now - self.window_seconds
        while queue and queue[0] <= boundary:
            queue.popleft()
        return queue

    async def check(self, key: str) -> None:
        """记录一次命中；超出窗口配额时抛出 429。"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        async with self._lock:
            now = time.monotonic()
            queue = self._evict_queue(self._hits[key], now)
            if len(queue) >= self.times:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)
            queue.append(now)

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.cleanup_interval_seconds)
            async with self._lock:
                now = time.monotonic()
                for key in [k for k, q in self._hits.items() if not self._evict_queue(q, now)]:
                    del self._hits[key]


def request_limit_key(request: Request) -> str:
    """默认限流维度：IP + User-Agent。UA 变化会重置配额，但登录接口本就要求同浏览器，可接受。"""
    ip = request.client.host if request.client else "unknown"
    return f"{ip}|{request.headers.get('User-Agent', '')}"


def rate_limit(times: int, window_seconds: float, key_func: Callable[[Request], str] = request_limit_key):
    """构造 FastAPI 依赖：按 `key_func` 维度对路由做滑动窗口限流。"""
    limiter = SlidingWindowRateLimiter(times, window_seconds)

    async def dependency(request: Request) -> None:
        await limiter.check(key_func(request))

    return Depends(dependency)
