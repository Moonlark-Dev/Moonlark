#  Moonlark - A new ChatBot
#  Copyright (C) 2024  Moonlark Development Team
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

import uuid
import asyncio

from fastapi import FastAPI, Request, HTTPException, status
from time import time
from typing import cast
from nonebot import get_app
from src.plugins.nonebot_plugin_larkuser import get_user, MoonlarkUser

from ..session import get_user_data
from ..config import config


app = cast(FastAPI, get_app())
bind_cache = {}


async def clean_cache(key: str) -> None:
    await asyncio.sleep(config.unused_session_remove_delay + 3)
    try:
        if time() >= bind_cache[key]["expired_at"]:
            bind_cache.pop(key)
    except KeyError:
        pass


@app.post("/api/users/{user_id}/sub-account/bind")
async def _(request: Request, user_id: str, current_user: MoonlarkUser = get_user_data()) -> dict:
    target_user = await get_user(user_id)
    if not target_user.is_registered():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not target_user.is_main_account():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not current_user.is_main_account():
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    if user_id in bind_cache or current_user.user_id in bind_cache:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    c = {
        "activate_code": uuid.uuid4().hex[:8],
        "account": current_user.user_id,
        "expired_at": time() + config.unused_session_remove_delay,
    }
    bind_cache[user_id] = c
    asyncio.create_task(clean_cache(user_id))
    return c


def get_bind_cache(key: str) -> dict:
    return bind_cache[key]
