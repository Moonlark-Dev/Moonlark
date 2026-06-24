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

from typing import Sequence

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import on_alconna, Alconna, UniMessage, Reply
from nonebot_plugin_htmlrender import md_to_pic
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_openai.utils.message import get_message
from nonebot_plugin_openai import fetch_message
from nonebot_plugin_message_summary.models import GroupMessage
from nonebot_plugin_chat.utils.group import parse_message_to_string
from sqlalchemy import select

from .utils import WdymTools

lang = LangHelper()

wdym = on_alconna(Alconna("wdym"))


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

    # 2. 获取上下文消息（最近 6 条）
    context_messages: Sequence[GroupMessage] = []
    try:
        recent = (
            await session.scalars(
                select(GroupMessage)
                .where(GroupMessage.group_id == group_id)
                .order_by(GroupMessage.id_.desc())
                .limit(6)
            )
        ).all()
        context_messages = list(recent)[::-1]  # 按时间正序
    except Exception as e:
        logger.exception(f"Failed to fetch context messages: {e}")

    # 3. 获取被回复消息的文本内容
    reply = uni_msg[Reply, 0]
    replied_text = await parse_message_to_string(UniMessage([reply]), event, bot, state, user_id)
    context_str = ""
    if context_messages:
        context_lines = [f"[{msg.sender_nickname}]: {msg.message}" for msg in context_messages]
        context_str = "\n".join(context_lines)

    # 4. 创建 AI 会话并获取解释
    system_message = await get_message("system", "wdym/system.md.jinja")
    user_message = await get_message(
        "user", "wdym/user.md.jinja",
        replied_text=replied_text,
        context=context_str,
        context_messages_count=len(context_messages),
    )
    tools = await WdymTools(user_id).get_tools()

    try:
        result = await fetch_message(
            messages=[system_message, user_message],
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