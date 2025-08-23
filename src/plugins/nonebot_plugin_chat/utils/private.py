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
from datetime import datetime
from typing import List

from nonebot_plugin_orm import async_scoped_session, AsyncSession, get_session
from sqlalchemy import select

from nonebot_plugin_openai.types import Messages
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message

from ..lang import lang
from ..models import SessionMessage, ChatUser


def generate_message_string(messages: Messages) -> str:
    m = []
    for msg in messages:
        if msg["role"] != "system":
            m.append(f"- {msg['role']}: {msg['content']}")
    return "\n".join(m)


async def get_history(session: async_scoped_session | AsyncSession, user_id: str) -> Messages:
    messages = []
    for message in await session.scalars(
        select(SessionMessage).where(SessionMessage.user_id == user_id).order_by(SessionMessage.id_)
    ):
        messages.append(generate_message(message.content, message.role))
    return messages


async def get_memory(user_id: str, session: async_scoped_session | AsyncSession) -> str:
    """获取用户记忆 - 现在只返回空字符串，因为已移除传统记忆"""
    return "None"


async def get_relevant_memories(context_id: str, text: str, max_memories: int = 3) -> List[str]:
    """获取与文本相关的记忆"""
    from .memory_graph import MemoryGraph

    memory_graph = MemoryGraph(context_id)
    await memory_graph.load_from_db()

    # 从文本中提取关键词
    topics = extract_topics_from_text(text)

    relevant_memories = []
    for topic in topics:
        memories = memory_graph.get_related_memories(topic, max_depth=2)
        for concept, memory_content in memories:
            if memory_content not in relevant_memories:
                relevant_memories.append(memory_content)
                if len(relevant_memories) >= max_memories:
                    break
        if len(relevant_memories) >= max_memories:
            break

    return relevant_memories


async def generate_history(user_id: str, session: async_scoped_session) -> Messages:
    from .memory_activator import memory_activator

    # 获取最近几条消息作为上下文
    recent_messages = await session.scalars(
        select(SessionMessage).where(SessionMessage.user_id == user_id).order_by(SessionMessage.id_.desc()).limit(5)
    )
    recent_context = " ".join([msg.content for msg in recent_messages])

    # 激活相关记忆
    activated_memories = await memory_activator.activate_memories_from_text(
        context_id=user_id, target_message=recent_context, max_memories=3
    )

    # 构建记忆文本
    memory_text_parts = []

    if activated_memories:
        memory_text_parts.append("相关记忆:")
        for concept, memory_content in activated_memories:
            memory_text_parts.append(f"- {concept}: {memory_content}")

    final_memory_text = "\n".join(memory_text_parts) if memory_text_parts else "None"

    text = await lang.text("prompt.default", user_id, final_memory_text)
    session.add(SessionMessage(user_id=user_id, content=text, role="system"))
    return [generate_message(text, "system")]


async def generate_memory(user_id: str) -> None:
    from .memory_graph import MemoryGraph

    async with get_session() as session:
        messages = await get_history(session, user_id)
        message_string = generate_message_string(messages)

        # 使用新的记忆图系统
        memory_graph = MemoryGraph(user_id)
        await memory_graph.load_from_db()

        # 从消息历史构建记忆
        await memory_graph.build_memory_from_text(message_string, compress_rate=0.1)

        # 保存记忆图到数据库
        await memory_graph.save_to_db()

        # 确保用户存在于数据库中（移除了memory字段更新）
        user_data = await session.get(ChatUser, {"user_id": user_id})
        if user_data is None:
            user_data = ChatUser(user_id=user_id, latest_chat=datetime.now())
            await session.merge(user_data)

        # 清除已处理的消息
        for message in await session.scalars(
            select(SessionMessage).where(SessionMessage.user_id == user_id).order_by(SessionMessage.id_)
        ):
            await session.delete(message)
        await session.commit()
