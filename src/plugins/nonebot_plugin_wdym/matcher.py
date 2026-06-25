#  Moonlark - A new ChatBot
#  Copyright (C) 2025  Moonlark Development Team
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

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.typing import T_State
from nonebot_plugin_alconna import on_alconna, Alconna, UniMessage, Reply
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_openai.utils.message import get_messages
from nonebot_plugin_openai import fetch_message
from nonebot_plugin_message_summary.models import GroupMessage
from nonebot_plugin_chat.utils.group import parse_message_to_string
from nonebot_plugin_chat.utils.message import parse_dict_message
from sqlalchemy import select

from .utils import WdymTools

lang = LangHelper()

wdym = on_alconna(Alconna("wdym"))


async def _get_replied_raw_text(bot: Bot, event: Event, state: T_State, reply: Reply, user_id: str) -> str | None:
    """获取被回复消息的原始文本（无 Reply 包装），用于匹配 GroupMessage"""
    # OB11：用 get_msg 拿到原始消息，再用 parse_message_to_string 解析为纯文本
    if isinstance(bot, OB11Bot) and reply.id is not None:
        try:
            result = await bot.get_msg(message_id=int(reply.id))
            return await parse_message_to_string(
                await parse_dict_message(result["message"], bot), event, bot, state, user_id
            )
        except Exception as e:
            logger.exception(f"Failed to get raw replied message: {e}")
            return None
    # 其他平台：reply.msg 如果已经是字符串就直接用
    if isinstance(reply.msg, str):
        return reply.msg
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
        # 最近 2 天内按内容精确匹配被回复消息，取最新的匹配
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
            # 用 id_ 精确取目标前 5 条
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
            return [*reversed(before), target_msg]

    # 匹配失败或无法获取原文：回退到最近 10 条
    recent = (
        await session.scalars(
            select(GroupMessage).where(GroupMessage.group_id == group_id).order_by(GroupMessage.id_.desc()).limit(10)
        )
    ).all()
    return list(recent)[::-1]


@wdym.handle()
async def handle_wdym(
    bot: Bot,
    event: Event,
    state: T_State,
    session: async_scoped_session,
    user_id: str = get_user_id(),
    group_id: str = get_group_id(),
) -> None:
    """处理 /wdym 命令 - 解释消息中的晦涩内容"""

    # 1. 获取被回复的消息
    original_msg = event.get_message()
    uni_msg = UniMessage.of(original_msg, bot)
    await uni_msg.attach_reply(event, bot)

    if not uni_msg.has(Reply):
        await lang.finish("no_reply", user_id)

    reply = uni_msg[Reply, 0]

    # 2. 获取被回复消息的原始文本
    replied_raw = await _get_replied_raw_text(bot, event, state, reply, user_id)

    # 3. 获取上下文消息（精确匹配）
    context_messages: list[GroupMessage] = []
    try:
        context_messages = await _query_context_messages(session, group_id, replied_raw)
    except Exception as e:
        logger.exception(f"Failed to fetch context messages: {e}")

    # 4. 构建 AI 提示词
    replied_text = await parse_message_to_string(UniMessage([reply]), event, bot, state, user_id)
    context_str = ""
    if context_messages:
        context_lines = [f"[{msg.sender_nickname}]: {msg.message}" for msg in context_messages]
        context_str = "\n".join(context_lines)

    messages = await get_messages(
        "wdym",
        replied_text=replied_text,
        context=context_str,
        context_messages_count=len(context_messages),
    )
    tools = await WdymTools(user_id).get_tools()

    try:
        result = await fetch_message(
            messages=messages,
            functions=tools,
            identify="WDYM",
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

    await wdym.finish(UniMessage().image(raw=image_bytes))
