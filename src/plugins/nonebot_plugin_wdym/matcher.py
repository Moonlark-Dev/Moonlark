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

from nonebot import on_command, logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larklang import LangHelper
from nonebot.typing import T_State
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot.params import Depends
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_openai.utils.message import get_messages
from nonebot_plugin_openai import fetch_message
from nonebot_plugin_message_summary.models import GroupMessage
from sqlalchemy import select

from .utils import WdymTools

lang = LangHelper()

wdym = on_command("wdym")

from nonebot.adapters.onebot.v11 import MessageEvent as OB11MessageEvent

async def _get_reply_message_id(event: Event, bot: Bot) -> Optional[int]:
    """Get the replied message ID from the event"""
    # if hasattr(event, "reply") and event.reply is not None:
    #     return event.reply.message_id
    # return None
    if isinstance(event, OB11MessageEvent) and event.reply:
        return event.reply.message_id


async def _get_replied_raw_text(bot: Bot, reply_msg_id: int) -> str | None:
    """获取被回复消息的原始文本"""
    if not isinstance(bot, OB11Bot):
        return None
    try:
        result = await bot.get_msg(message_id=reply_msg_id)
        return str(result.get("message", ""))
    except Exception as e:
        logger.exception(f"Failed to get raw replied message: {e}")
        return None


async def _query_context_messages(
    session: async_scoped_session,
    group_id: str,
    replied_raw_text: str | None,
) -> list[GroupMessage]:
    """获取上下文消息

    1. 有原文时：最近 2 天内按内容匹配，取目标 id_ 的前 5 条
    2. 匹配失败或无法获取原文时：回退到最近 10 条
    """
    if replied_raw_text:
        two_days_ago = datetime.now() - timedelta(days=2)
        target_id = await session.scalar(
            select(GroupMessage.id_)
            .where(
                GroupMessage.group_id == group_id,
                GroupMessage.message == replied_raw_text,
                GroupMessage.timestamp >= two_days_ago,
            )
            .order_by(GroupMessage.id_.desc())
            .limit(1)
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
                    .limit(5)
                )
            ).all()
            target_msg = await session.get(GroupMessage, target_id)
            messages = [*reversed(before)]
            if target_msg is not None:
                messages.append(target_msg)
            return messages

    recent = (
        await session.scalars(
            select(GroupMessage).where(GroupMessage.group_id == group_id).order_by(GroupMessage.id_.desc()).limit(10)
        )
    ).all()
    return list(recent)[::-1]


async def get_replied_raw(state: T_State, bot: Bot, event: Event, user_id: str = get_user_id()) -> str:
    # 1. 获取被回复的消息 ID
    reply_msg_id = await _get_reply_message_id(event, bot)
    if reply_msg_id is None:
        await lang.finish("no_reply", user_id)
    # 2. 获取被回复消息的原始文本
    replied_raw = await _get_replied_raw_text(bot, reply_msg_id)
    if replied_raw is None:
        await lang.finish("get_reply_failed", user_id)
    state["replied_raw"] = replied_raw
    return replied_raw


async def get_context_str(state: T_State, session: async_scoped_session, group_id: str = get_group_id()) -> Optional[str]:
    replied_raw = state.get("replied_raw")
    context_messages: list[GroupMessage] = []
    try:
        context_messages = await _query_context_messages(session, group_id, replied_raw)
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
    context_str: str  = Depends(get_context_str)
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
        result = await fetch_message(
            messages=messages,
            functions=tools,
            identify="WDYM",
            reasoning_effort="high"
        )
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
