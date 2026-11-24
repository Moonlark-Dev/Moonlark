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
from nonebot_plugin_bots import get_group_bind_by_ob11_group, get_group_bind_by_qqbot_group
from nonebot_plugin_larkuser.user.utils import is_user_registered
from nonebot_plugin_larkutils import set_main_account
from nonebot_plugin_userinfo import UserInfo, get_user_info
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


def _get_raw_group_id(adapter_type: str, event: Event) -> Optional[str]:
    """取事件所属群的原始 ID：OneBot 11 为群号，QQ 官方为 group_openid；私聊返回 None。"""
    if adapter_type == "onebot_v11":
        group_id = getattr(event, "group_id", None)
        if group_id is not None:
            return str(group_id)
    elif adapter_type == "qq":
        group_openid = getattr(event, "group_openid", None)
        if isinstance(group_openid, str) and group_openid:
            return group_openid
    return None


async def _resolve_auto_bind_group(adapter_type: str, event: Event) -> tuple[bool, Optional[str]]:
    """解析本次消息所属的 auto bind 作用域。

    返回 ``(allowed, group_key)``：

    - 私聊：``(True, None)``，保持原有行为；
    - 已双向绑定（OneBot 11 群号与 QQ 官方 group_openid 都在 GroupBind 里）的群：
      ``(True, OneBot 11 群号)``，两个适配器的事件按同一个群号配对；
    - 未绑定或只完成单边绑定的群：``(False, None)``，关闭 auto bind。

    群内没有在线 OneBot 11 bot 时，OneBot 11 侧不会产生任何消息事件，按群号隔离匹配后
    该群自然也无法完成绑定，因此不需要额外的在线状态判断（也没有可靠的内存数据可以判断）。
    """
    raw_group_id = _get_raw_group_id(adapter_type, event)
    if raw_group_id is None:
        return True, None
    if adapter_type == "onebot_v11":
        bind = await get_group_bind_by_ob11_group(raw_group_id)
        if bind is None or not bind.group_openid:
            logger.debug("Auto-bind disabled: OneBot 11 group %s is not fully bound", raw_group_id)
            return False, None
        return True, raw_group_id
    bind = await get_group_bind_by_qqbot_group(raw_group_id)
    if bind is None or not bind.group_qq_number:
        logger.debug("Auto-bind disabled: QQ group %s is not fully bound", raw_group_id)
        return False, None
    return True, bind.group_qq_number


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


def _find_cache_match(
    adapter_type: str,
    group_key: Optional[str],
    plain_text: str,
    avatar_hash: str,
    now: datetime,
) -> Optional[dict]:
    for cached in _recent_messages:
        if cached["adapter"] == adapter_type:
            continue
        if cached["group_key"] != group_key:
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


def _add_to_cache(
    adapter_type: str,
    group_key: Optional[str],
    user_id: str,
    plain_text: str,
    avatar_hash: str,
    now: datetime,
) -> None:
    _recent_messages.append(
        {
            "adapter": adapter_type,
            "group_key": group_key,
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
async def _(bot: Bot, event: Event) -> None:
    adapter_type = _get_adapter_type(bot)
    if adapter_type is None:
        return

    try:
        plain_text = event.get_plaintext().strip()
    except (NotImplementedError, ValueError):
        return

    if not plain_text:
        return

    try:
        allowed, group_key = await _resolve_auto_bind_group(adapter_type, event)
    except Exception:
        # 群绑定查询失败时不要阻断消息处理，跳过本次自动绑定即可
        logger.exception("Failed to resolve group binding for auto-bind")
        return
    if not allowed:
        return

    try:
        user_id = event.get_user_id()
        user_info = await get_user_info(bot, event, user_id)
    except (ValueError, NotImplementedError):
        return
    if user_info is None:
        return

    avatar_hash = await _get_avatar_hash(user_info)
    if not avatar_hash:
        return

    now = datetime.now(timezone.utc)

    async with _cache_lock:
        cached = _find_cache_match(adapter_type, group_key, plain_text, avatar_hash, now)
        if cached is None:
            _add_to_cache(adapter_type, group_key, user_id, plain_text, avatar_hash, now)
            return

        if adapter_type == "qq":
            qq_openid, ob11_user_id = user_id, cached["user_id"]
        else:
            qq_openid, ob11_user_id = cached["user_id"], user_id

        _recent_messages.remove(cached)

    try:
        await _try_bind(qq_openid, ob11_user_id)
    except Exception:
        logger.exception("Failed to auto-bind %s to %s", qq_openid, ob11_user_id)
