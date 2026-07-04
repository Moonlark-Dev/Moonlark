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

from datetime import datetime, timedelta
from typing import Optional

from nonebot import logger, on_command
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import (
    Bot as OB11Bot,
    Message as OB11Message,
    MessageEvent as OB11MessageEvent,
    MessageSegment as OB11Segment,
)
from nonebot.params import Depends
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_chat.utils import parse_message_to_string
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_message_summary.hash_utils import compute_message_hash
from nonebot_plugin_message_summary.models import GroupMessage
from nonebot_plugin_openai import fetch_message
from nonebot_plugin_openai.utils.message import get_messages
from nonebot_plugin_orm import async_scoped_session
from sqlalchemy import select

from .utils import WdymTools

lang = LangHelper()

wdym = on_command("wdym")


async def _get_reply_message_id(event: Event, bot: Bot) -> Optional[int]:
    """Get the replied message ID from the event"""
    # if hasattr(event, "reply") and event.reply is not None:
    #     return event.reply.message_id
    # return None
    if isinstance(event, OB11MessageEvent) and event.reply:
        return event.reply.message_id


async def _get_replied_message_hash(
    bot: Bot,
    reply_msg_id: int,
    event: Event,
    state: T_State,
    lang_str: str,
    session: async_scoped_session,
) -> tuple[bytes | None, str | None]:
    """获取被回复消息的 hash 和原始文本

    Returns:
        (message_hash, raw_text) - hash 和原始文本
    """
    if not isinstance(bot, OB11Bot):
        return None, None
    try:
        result = await bot.get_msg(message_id=reply_msg_id)
        message_data = result.get("message", "")
        if isinstance(message_data, list):
            try:
                msg = OB11Message([OB11Segment(**seg) for seg in message_data])
            except Exception:
                msg = OB11Message(str(message_data))
        else:
            msg = OB11Message(str(message_data))
        message_hash = compute_message_hash(msg)

        group_msg = await session.scalar(
            select(GroupMessage)
            .where(GroupMessage.message_hash == message_hash)
            .order_by(GroupMessage.id_.desc())
            .limit(1),
        )
        if group_msg is not None:
            raw_text = group_msg.message
        else:
            raw_text = await parse_message_to_string(
                UniMessage.generate_without_reply(message=msg, bot=bot), event, bot, state, lang_str
            )
        return message_hash, raw_text
    except Exception as e:
        logger.exception(f"Failed to get replied message hash: {e}")
        return None, None


async def _query_context_messages(
    session: async_scoped_session,
    group_id: str,
    replied_message_hash: bytes | None,
) -> list[GroupMessage]:
    """获取上下文消息

    1. 有原文 hash 时：最近 2 天内按 hash 匹配，取目标 id_ 的前 5 条
    2. 匹配失败或无法获取原文时：回退到最近 10 条
    """
    if replied_message_hash:
        two_days_ago = datetime.now() - timedelta(days=2)
        target_id = await session.scalar(
            select(GroupMessage.id_)
            .where(
                GroupMessage.group_id == group_id,
                GroupMessage.message_hash == replied_message_hash,
                GroupMessage.timestamp >= two_days_ago,
            )
            .order_by(GroupMessage.id_.desc())
            .limit(1),
        )

        if target_id is not None:
            before = (
                await session.scalars(
                    select(GroupMessage)
                    .where(
                        GroupMessage.group_id == group_id,
                        GroupMessage.id_ < target_id,
                    )
                    .order_by(GroupMessage.id_.desc())
                    .limit(5),
                )
            ).all()
            target_msg = await session.get(GroupMessage, target_id)
            messages = [*reversed(before)]
            if target_msg is not None:
                messages.append(target_msg)
            return messages

    recent = (
        await session.scalars(
            select(GroupMessage).where(GroupMessage.group_id == group_id).order_by(GroupMessage.id_.desc()).limit(10),
        )
    ).all()
    return list(recent)[::-1]


async def get_replied_raw(
    state: T_State,
    bot: Bot,
    event: Event,
    session: async_scoped_session,
    user_id: str = get_user_id(),
) -> str:
    # 1. 获取被回复的消息 ID
    reply_msg_id = await _get_reply_message_id(event, bot)
    if reply_msg_id is None:
        await lang.finish("no_reply", user_id)
    # 2. 获取被回复消息的 hash 和原始文本
    replied_hash, replied_raw = await _get_replied_message_hash(bot, reply_msg_id, event, state, user_id, session)
    if replied_hash is None:
        await lang.finish("get_reply_failed", user_id)
    state["replied_hash"] = replied_hash
    return replied_raw or ""


async def get_context_str(
    state: T_State,
    session: async_scoped_session,
    group_id: str = get_group_id(),
) -> Optional[str]:
    replied_hash = state.get("replied_hash")
    context_messages: list[GroupMessage] = []
    try:
        context_messages = await _query_context_messages(session, group_id, replied_hash)
    except Exception as e:
        logger.exception(f"Failed to fetch context messages: {e}")
    state["context_length"] = len(context_messages)
    if context_messages:
        context_lines = [f"[{msg.sender_nickname}]: {msg.message}" for msg in context_messages]
        return "\n".join(context_lines)


@wdym.handle()
async def handle_wdym(
    state: T_State,
    user_id: str = get_user_id(),
    replied_text: str = Depends(get_replied_raw),
    context_str: str = Depends(get_context_str),
) -> None:
    """处理 /wdym 命令 - 解释消息中的晦涩内容"""
    messages = await get_messages(
        "wdym",
        replied_text=replied_text,
        context=context_str,
        context_messages_count=state["context_length"],
    )
    tools = await WdymTools(user_id).get_tools()

    try:
        result = await fetch_message(messages=messages, functions=tools, identify="WDYM", reasoning_effort="high")
    except Exception as e:
        logger.exception(f"WDYM AI request failed: {e}")
        await lang.finish("ai_error", user_id)

    # 5. 渲染为图片并发送
    try:
        image_bytes = await md_to_pic(result)
    except Exception as e:
        logger.exception(f"Failed to render markdown: {e}")
        await wdym.finish(result)

    await wdym.finish(await UniMessage().image(raw=image_bytes).export())
