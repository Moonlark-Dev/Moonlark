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
# ##############################################################################

import time
from typing import cast

from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app
from nonebot_plugin_larkuid.session import get_user_id

from .config import config
from .store import clear_announcement, load_announcement, save_announcement
from .types import UpdateAnnouncement, UpdateAnnouncementInput

app = cast(FastAPI, get_app())


@app.get("/api/updates/latest")
async def get_latest(request: Request) -> dict:
    """获取最新更新公告（公开接口）"""
    announcement = await load_announcement()
    return {"announcement": announcement.model_dump() if announcement else None}


@app.get("/api/updates/settings")
async def read_settings(request: Request, user_id: str = get_user_id()) -> dict:
    """读取当前更新公告（仅超管，供公告设置页回填）"""
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    announcement = await load_announcement()
    return {"announcement": announcement.model_dump() if announcement else None}


@app.put("/api/updates/settings")
async def update_settings(
    request: Request, announcement_input: UpdateAnnouncementInput, user_id: str = get_user_id()
) -> dict:
    """发布新的更新公告（仅超管）：每次保存都会生成新的 update_id，用户端因此产生新提醒"""
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    if not announcement_input.title.strip() or not announcement_input.content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "标题和正文不能为空")
    if any(not button.label.strip() or not button.text.strip() for button in announcement_input.buttons):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "按钮的名称和指令不能为空")
    previous = await load_announcement()
    new_announcement = UpdateAnnouncement(
        update_id=previous.update_id + 1 if previous else 1,
        title=announcement_input.title.strip(),
        content=announcement_input.content,
        buttons=announcement_input.buttons,
        time=time.time(),
    )
    await save_announcement(new_announcement)
    return {"success": True, "update_id": new_announcement.update_id}


@app.delete("/api/updates/settings")
async def delete_settings(request: Request, user_id: str = get_user_id()) -> dict:
    """清除当前更新公告（仅超管）"""
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    await clear_announcement()
    return {"success": True}
