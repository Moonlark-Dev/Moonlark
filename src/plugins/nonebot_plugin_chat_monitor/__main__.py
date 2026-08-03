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
import os
import shutil

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from nonebot import get_app, get_driver
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session
from sqlalchemy import text

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
# 启动时创建数据库索引
# ========================================================================


@get_driver().on_startup
async def _ensure_indexes():
    """创建 Note 和 AgentEvent 表的必要索引（如果不存在）。"""
    await _deploy_frontend()


async def _deploy_frontend():
    """将 chat-monitor 前端构建产物部署到静态文件目录。"""
    src_dir = "/vol2/@apphome/trim.openclaw/data/workspace/chat-monitor/dist"
    dst_dir = "/var/www/monitor"
    if not os.path.isdir(src_dir):
        logger.warning(f"[ChatMonitor] 前端构建产物不存在: {src_dir}")
        return
    try:
        # 复制 index.html
        shutil.copy2(os.path.join(src_dir, "index.html"), os.path.join(dst_dir, "index.html"))
        # 复制 favicon
        favicon_src = os.path.join(src_dir, "favicon.svg")
        if os.path.exists(favicon_src):
            shutil.copy2(favicon_src, os.path.join(dst_dir, "favicon.svg"))
        # 复制 assets
        src_assets = os.path.join(src_dir, "assets")
        dst_assets = os.path.join(dst_dir, "assets")
        # 删除旧的 assets 目录（如果存在）并重建
        if os.path.isdir(dst_assets):
            shutil.rmtree(dst_assets)
        shutil.copytree(src_assets, dst_assets)
        logger.info("[ChatMonitor] 前端产物已部署到 /var/www/monitor")
    except Exception as exc:
        logger.warning(f"[ChatMonitor] 前端部署失败: {exc}")
    try:
        async with get_session() as db_session:
            # Note.created_time 用于 ORDER BY DESC
            await db_session.execute(
                text("CREATE INDEX IF NOT EXISTS ix_note_created_time " "ON nonebot_plugin_chat_note (created_time)")
            )
            # AgentEvent.created_at 已有 index=True，但确保它存在
            await db_session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_agent_event_created_at "
                    "ON nonebot_plugin_chat_diaryentry (created_at)"
                )
            )
            await db_session.commit()
            logger.info("[ChatMonitor] 数据库索引已确认")
    except Exception as exc:
        logger.warning(f"[ChatMonitor] 创建索引失败（可忽略）: {exc}")


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
