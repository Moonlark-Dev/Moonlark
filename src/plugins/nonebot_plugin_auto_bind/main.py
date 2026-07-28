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
from typing import Optional

from nonebot.adapters import Bot, Event  # ruff:ignore[typing-only-third-party-import]
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot.message import event_preprocessor
from nonebot_plugin_larkuser.user.utils import is_user_registered
from nonebot_plugin_larkutils import set_main_account
from nonebot_plugin_userinfo import EventUserInfo, UserInfo
from PIL import Image

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


async def _get_avatar_hash(user_info: UserInfo) -> str:
    avatar = user_info.user_avatar
    if avatar is None:
        return ""
    try:
        avatar_bytes = await avatar.get_image()
    except Exception:
        return ""
    if not avatar_bytes:
        return ""
    try:
        img = Image.open(BytesIO(avatar_bytes)).convert("RGB")
        img = img.resize((64, 64), Image.LANCZOS)
        return hashlib.md5(img.tobytes(), usedforsecurity=False).hexdigest()
    except Exception:
        return ""


def _find_cache_match(adapter_type: str, plain_text: str, avatar_hash: str, now: datetime) -> Optional[dict]:
    for cached in _recent_messages:
        if cached["adapter"] == adapter_type:
            continue
        if now - cached["timestamp"] > _TIME_THRESHOLD:
            continue
        if cached["plain_text"] != plain_text:
            continue
        if cached["avatar_hash"] != avatar_hash:
            continue
        return cached
    return None


async def _try_bind(qq_openid: str, ob11_user_id: str) -> None:
    if await is_user_registered(qq_openid, include_subaccount=False):
        return
    await set_main_account(qq_openid, ob11_user_id)
    logger.info("Auto-bound QQ OpenID %s to OneBot 11 User ID %s", qq_openid, ob11_user_id)


def _add_to_cache(adapter_type: str, user_id: str, plain_text: str, avatar_hash: str, now: datetime) -> None:
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


@event_preprocessor
async def _(bot: Bot, event: Event, user_info: UserInfo = EventUserInfo()) -> None:
    adapter_type = _get_adapter_type(bot)
    if adapter_type is None:
        return

    try:
        plain_text = event.get_plaintext().strip()
    except NotImplementedError:
        return

    if not plain_text:
        return

    avatar_hash = await _get_avatar_hash(user_info)
    if not avatar_hash:
        return

    now = datetime.now(timezone.utc)
    user_id = event.get_user_id()

    async with _cache_lock:
        cached = _find_cache_match(adapter_type, plain_text, avatar_hash, now)
        if cached is None:
            _add_to_cache(adapter_type, user_id, plain_text, avatar_hash, now)
            return

        if adapter_type == "qq":
            qq_openid, ob11_user_id = user_id, cached["user_id"]
        else:
            qq_openid, ob11_user_id = cached["user_id"], user_id

        _recent_messages.remove(cached)

    await _try_bind(qq_openid, ob11_user_id)
