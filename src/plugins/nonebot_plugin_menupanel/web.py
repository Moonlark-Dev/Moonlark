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
from .models import MenuPanelSettings
from .store import load_settings, save_settings

app = cast(FastAPI, get_app())

# 菜单固定项（帮助、在线帮助）之外可配置的指令数量上限（QQ 菜单顶层最多 10 项）
MAX_COMMANDS = 8


@app.get("/api/menupanel/permission")
async def get_permission(request: Request, user_id: str = get_user_id()) -> dict[str, bool]:
    return {"superuser": user_id in config.superusers}


@app.get("/api/menupanel/settings")
async def read_settings(request: Request, user_id: str = get_user_id()) -> MenuPanelSettings:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return await load_settings()


@app.put("/api/menupanel/settings")
async def update_settings(
    request: Request, settings: MenuPanelSettings, user_id: str = get_user_id()
) -> dict[str, bool]:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    from nonebot_plugin_larkhelp.__main__ import get_help_list

    help_list = get_help_list()
    unknown = [command for command in settings.commands if command not in help_list]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知指令: {', '.join(unknown)}")
    # 去重保序，且不允许展示超管专属指令
    commands = list(
        dict.fromkeys(command for command in settings.commands if help_list[command].category != "superuser")
    )
    if len(commands) > MAX_COMMANDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"最多选择 {MAX_COMMANDS} 个指令")
    await save_settings(MenuPanelSettings(commands=commands, updated_at=time.time()))
    return {"success": True}


@app.post("/api/menupanel/sync")
async def trigger_sync(request: Request, user_id: str = get_user_id()) -> dict:
    if user_id not in config.superusers:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    from .sync import sync_all

    settings = await load_settings()
    results = await sync_all(settings)
    return {
        "success": all(result.success for result in results),
        "results": [result.model_dump() for result in results],
    }
