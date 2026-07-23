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
from typing import Any

from fastapi import WebSocket
from nonebot.log import logger


class ConnectionManager:
    """管理 WebSocket 连接，广播状态更新。"""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    @property
    def connections(self) -> list[WebSocket]:
        """当前活跃的连接列表（只读视图）"""
        return list(self._connections)

    @property
    def count(self) -> int:
        """当前连接数"""
        return len(self._connections)

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info(f"[ChatMonitor] WebSocket 客户端已连接，当前 {self.count} 个连接")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info(f"[ChatMonitor] WebSocket 客户端已断开，当前 {self.count} 个连接")

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
                self._connections.remove(ws)


ws_manager = ConnectionManager()
