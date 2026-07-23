#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""WebSocket 连接管理器"""

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket
from nonebot.log import logger


class _RateLimiter:
    """简易 IP 级别频率限制。"""

    def __init__(self, max_per_minute: int = 10):
        self._max = max_per_minute
        self._buckets: dict[str, list[float]] = {}

    def check(self, ip: str) -> bool:
        now = time.monotonic()
        timestamps = self._buckets.get(ip, [])
        # 清除 60 秒前的记录
        timestamps = [t for t in timestamps if now - t < 60]
        if len(timestamps) >= self._max:
            return False
        timestamps.append(now)
        self._buckets[ip] = timestamps
        return True


class ConnectionManager:
    """管理 WebSocket 连接，广播状态更新。"""

    def __init__(self):
        self._connections: dict[WebSocket, str] = {}  # ws -> client_ip
        self._lock = asyncio.Lock()
        self._rate_limiter = _RateLimiter(max_per_minute=15)
        self._monitor_task: asyncio.Task | None = None

    @property
    def connections(self) -> list[WebSocket]:
        """当前活跃的连接列表（只读视图）"""
        return list(self._connections.keys())

    @property
    def count(self) -> int:
        """当前连接数"""
        return len(self._connections)

    async def connect(self, ws: WebSocket, client_ip: str = "") -> bool:
        """尝试接受 WebSocket 连接。被限流时返回 False。"""
        if not self._rate_limiter.check(client_ip):
            await ws.close(code=4003, reason="Rate limited, try again later")
            logger.warning(f"[ChatMonitor] 拒绝来自 {client_ip} 的连接（限流）")
            return False

        await ws.accept()
        async with self._lock:
            self._connections[ws] = client_ip
        logger.info(f"[ChatMonitor] WebSocket 客户端已连接（{client_ip}），当前 {self.count} 个连接")

        # 启动服务端保活监控（仅首次连接时）
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._keepalive_loop())

        return True

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            ip = self._connections.pop(ws, "")
        logger.info(f"[ChatMonitor] WebSocket 客户端已断开（{ip}），当前 {self.count} 个连接")

    async def broadcast(self, data: dict[str, Any]):
        """向所有连接的客户端广播消息。"""
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                ip = self._connections.pop(ws, "")
                logger.debug(f"[ChatMonitor] 广播时清理死连接（{ip}）")

    async def _keepalive_loop(self):
        """服务端保活：每 30 秒发送 ping，移除无响应的连接。"""
        while True:
            await asyncio.sleep(30)
            async with self._lock:
                dead: list[WebSocket] = []
                for ws in self._connections:
                    try:
                        await ws.send_json({"type": "ping"})
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    ip = self._connections.pop(ws, "")
                    if ip:
                        logger.debug(f"[ChatMonitor] 保活检测到死连接（{ip}）")
            if not self._connections:
                self._monitor_task = None
                break


ws_manager = ConnectionManager()
