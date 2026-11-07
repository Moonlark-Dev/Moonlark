"""更新公告 Web 接口

原 ``nonebot_plugin_updates`` 的 ``/api/updates/*`` 接口整体搬到 broadcast，
路径保持不变，前端无需改动。
"""

import time
from typing import cast

from fastapi import FastAPI, HTTPException, Request, status
from nonebot import get_app
from nonebot_plugin_larkuid.session import get_user_id

from .announcement import clear_announcement, load_announcement, save_announcement
from .announcement import UpdateAnnouncement, UpdateAnnouncementInput
from .config import config

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
