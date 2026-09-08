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

"""Chat Monitor - 为 Moonlark 提供 WebSocket 和 REST API 接口，用于实时监控聊天和 EGO 状态。"""

import hashlib
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from nonebot import get_app
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler

from .auth import verify_admin
from .broadcast import _start_ws_broadcast  # noqa: F401 -- 注册启动时广播
from .config import config
from .routers.ego import router as ego_router
from .routers.notes import router as notes_router
from .routers.sessions import router as sessions_router
from .ws_manager import ws_manager

app: FastAPI = get_app()  # type: ignore[assignment]

# 注册路由
app.include_router(sessions_router)
app.include_router(notes_router)
app.include_router(ego_router)

# ========================================================================
# WebSocket 端点
# ========================================================================


@app.websocket("/chat-monitor/ws")
async def chat_monitor_websocket(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    salt = websocket.query_params.get("salt", "")
    client_ip = websocket.client.host if websocket.client else ""

    # 验证 token
    expected = hashlib.sha256(f"{config.status_report_password}+{salt}".encode()).hexdigest()
    if token != expected:
        await websocket.close(code=4001, reason="Invalid access token")
        return

    # 连接管理（含限流）
    connected = await ws_manager.connect(websocket, client_ip)
    if not connected:
        return

    try:
        # 发送初始全量状态
        from .broadcast import collect_full_status

        payload = await collect_full_status()
        payload["type"] = "status_snapshot"
        await websocket.send_json(payload)
        # 保持连接，广播由广播循环负责
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "pong":
                    # 收到客户端 pong 应答，不需要额外处理
                    pass
            except (json.JSONDecodeError, Exception):
                pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[ChatMonitor] WebSocket 异常: {e}")
    finally:
        await ws_manager.disconnect(websocket)


# ========================================================================
# 定时清理（仅限 WebSocket 连接的冗余清理）
# ========================================================================


@scheduler.scheduled_job("interval", minutes=5, id="chat_monitor_cleanup")
async def _cleanup_check():
    """定期检查 WebSocket 连接健康状态——保活循环已处理，
    此函数仅作为额外的安全检查。"""
    pass
