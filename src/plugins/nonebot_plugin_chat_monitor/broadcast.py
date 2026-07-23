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

"""WebSocket 广播循环，每 2 秒收集全量状态并推送"""

import asyncio
from typing import Any

from nonebot import get_driver
from nonebot.log import logger

from .ws_manager import ws_manager


async def collect_full_status() -> dict[str, Any]:
    """收集前端需要的全量状态数据。"""
    # 延迟导入避免循环依赖
    from .routers.sessions import build_status

    return await build_status()


async def _ws_broadcast_loop():
    """每 2 秒收集并广播一次全量状态。"""
    await asyncio.sleep(3)  # 等待 NoneBot 完全初始化
    while True:
        try:
            if ws_manager._connections:
                payload = await collect_full_status()
                await ws_manager.broadcast(payload)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[ChatMonitor] 广播异常: {e}")
        await asyncio.sleep(2)


@get_driver().on_startup
async def _start_ws_broadcast():
    """在 NoneBot 启动后启动 WebSocket 广播循环。"""
    asyncio.create_task(_ws_broadcast_loop())
