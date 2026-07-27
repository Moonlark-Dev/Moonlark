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

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from io import BytesIO
from logging import getLogger
from typing import TYPE_CHECKING, Optional

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_larkuser.user.utils import is_user_registered
from nonebot_plugin_larkutils import set_main_account
from nonebot_plugin_userinfo import EventUserInfo, UserInfo
from PIL import Image

if TYPE_CHECKING:
    from nonebot.adapters import Bot, Event

logger = getLogger(__name__)

_MAX_CACHE_AGE = timedelta(seconds=2)
_TIME_THRESHOLD = timedelta(seconds=0.5)
_MAX_CACHE_SIZE = 200

_recent_messages: list[dict] = []
_cache_lock = asyncio.Lock()


def _get_adapter_type(bot: Bot) -> Optional[str]:
    if isinstance(bot, V11Bot):
        return "onebot_v11"
    if isinstance(bot, QQBot):
        return "qq"
    return None


def _hash_avatar(image_bytes: bytes) -> str:
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        img = img.resize((64, 64), Image.LANCZOS)
        return hashlib.md5(img.tobytes()).hexdigest()  # ruff:ignore[hashlib-insecure-hash-function]
    except Exception:
        return ""


auto_bind_matcher = on_message(block=False, priority=1)


@auto_bind_matcher.handle()
async def _(bot: Bot, event: Event, user_info: UserInfo = EventUserInfo()) -> None:
    adapter_type = _get_adapter_type(bot)
    if adapter_type is None:
        return

    plain_text = event.get_plaintext().strip()
    if not plain_text:
        return

    avatar = user_info.user_avatar
    if avatar is None:
        return

    try:
        avatar_bytes = await avatar.get_image()
    except Exception:
        return

    if not avatar_bytes:
        return

    avatar_hash = _hash_avatar(avatar_bytes)
    if not avatar_hash:
        return

    now = datetime.now(timezone.utc)
    user_id = event.get_user_id()

    async with _cache_lock:
        for cached in _recent_messages:
            if cached["adapter"] == adapter_type:
                continue
            if now - cached["timestamp"] > _TIME_THRESHOLD:
                continue
            if cached["plain_text"] != plain_text:
                continue
            if cached["avatar_hash"] != avatar_hash:
                continue

            if adapter_type == "qq":
                qq_openid = user_id
                ob11_user_id = cached["user_id"]
            else:
                qq_openid = cached["user_id"]
                ob11_user_id = user_id

            if await is_user_registered(qq_openid, include_subaccount=False):
                return

            try:
                await set_main_account(qq_openid, ob11_user_id)
                logger.info(
                    "Auto-bound QQ OpenID %s to OneBot 11 User ID %s",
                    qq_openid,
                    ob11_user_id,
                )
            except Exception:
                logger.warning(
                    "Failed to auto-bind QQ OpenID %s to OneBot 11 User ID %s",
                    qq_openid,
                    ob11_user_id,
                )

            _recent_messages.remove(cached)
            return

        _recent_messages.append(
            {
                "adapter": adapter_type,
                "user_id": user_id,
                "plain_text": plain_text,
                "avatar_hash": avatar_hash,
                "timestamp": now,
            },
        )

        cutoff = now - _MAX_CACHE_AGE
        _recent_messages[:] = [m for m in _recent_messages if m["timestamp"] > cutoff]

        if len(_recent_messages) > _MAX_CACHE_SIZE:
            _recent_messages[:] = _recent_messages[-_MAX_CACHE_SIZE:]
