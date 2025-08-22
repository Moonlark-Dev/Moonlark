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
import base64
import copy
import json
import traceback
from datetime import datetime
from typing import Optional

from nonebot import Bot, logger
from nonebot.internal.adapter import Event
from nonebot.typing import T_State
from nonebot_plugin_userinfo import get_user_info
from nonebot_plugin_alconna import Image, image_fetch, UniMessage, Text, At, Reply
from nonebot_plugin_orm import async_scoped_session, AsyncSession, get_session
from sqlalchemy import select

from nonebot_plugin_chat.lang import lang
from nonebot_plugin_chat.models import SessionMessage, ChatUser, ChatGroup
from nonebot_plugin_larkuser import get_user
from nonebot_plugin_larkutils import get_group_id, get_user_id
from nonebot_plugin_openai.types import Messages
from nonebot_plugin_openai.utils.chat import fetch_message
from nonebot_plugin_openai.utils.message import generate_message
import hashlib

import asyncio
import time
from collections import defaultdict
from typing import Any, Optional

class AsyncCache:
    def __init__(self, expiration_time: int = 60):
        """
        初始化缓存管理系统
        :param expiration_time: 缓存项的默认过期时间（秒）
        """
        self.cache = {}  # 存储缓存数据的字典
        self.expiration_time = expiration_time  # 缓存过期时间
        self.lock = asyncio.Lock()  # 异步锁，确保缓存操作的原子性
        # 启动异步任务来定期清理过期缓存
        asyncio.create_task(self.cleanup())

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存项，支持自动过期
        :param key: 缓存的键
        :param value: 缓存的值
        :param ttl: 缓存项的过期时间，默认为 None 使用默认的过期时间
        """
        ttl = ttl if ttl is not None else self.expiration_time
        expiration = time.time() + ttl  # 计算过期时间
        async with self.lock:
            self.cache[key] = {
                "value": value,
                "expiration": expiration
            }

    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存项的值
        :param key: 缓存的键
        :return: 缓存的值，若不存在或已过期返回 None
        """
        async with self.lock:
            cache_item = self.cache.get(key)
            if cache_item:
                # 检查是否过期
                if time.time() < cache_item["expiration"]:
                    return cache_item["value"]
                else:
                    # 缓存过期，删除该项
                    del self.cache[key]
            return None

    async def delete(self, key: str):
        """
        删除缓存项
        :param key: 缓存的键
        """
        async with self.lock:
            if key in self.cache:
                del self.cache[key]

    async def cleanup(self):
        """
        定期清理过期的缓存项
        """
        while True:
            await asyncio.sleep(30)  # 每30秒执行一次清理操作
            async with self.lock:
                # 当前时间
                current_time = time.time()
                # 清理所有过期的缓存项
                keys_to_delete = [key for key, item in self.cache.items() if item["expiration"] < current_time]
                for key in keys_to_delete:
                    del self.cache[key]


image_cache = AsyncCache(600)



async def get_history(session: async_scoped_session | AsyncSession, user_id: str) -> Messages:
    messages = []
    for message in await session.scalars(
        select(SessionMessage).where(SessionMessage.user_id == user_id).order_by(SessionMessage.id_)
    ):
        messages.append(generate_message(message.content, message.role))
    return messages


async def get_memory(user_id: str, session: async_scoped_session | AsyncSession) -> str:
    result = await session.get(ChatUser, {"user_id": user_id})
    if result:
        return result.memory
    return "None"


async def generate_history(user_id: str, session: async_scoped_session) -> Messages:
    text = await lang.text("prompt.default", user_id, await get_memory(user_id, session))
    session.add(SessionMessage(user_id=user_id, content=text, role="system"))
    return [generate_message(text, "system")]


def generate_message_string(messages: Messages) -> str:
    m = []
    for msg in messages:
        if msg["role"] != "system":
            m.append(f"- {msg['role']}: {msg['content']}")
    return "\n".join(m)


async def generate_memory(user_id: str) -> None:
    async with get_session() as session:
        messages = await get_history(session, user_id)
        message_string = generate_message_string(messages)
        memory = await fetch_message([
            generate_message(
                await lang.text("prompt.memory", user_id, await get_memory(user_id, session)), "system"
            ),
            generate_message(await lang.text("prompt.memory_2", user_id, message_string, "user")),
        ])
        user_data = await session.get(ChatUser, {"user_id": user_id})
        if user_data is None:
            user_data = ChatUser(user_id=user_id, memory="None", latest_chat=datetime.now())
        user_data.memory = memory
        await session.merge(user_data)
        for message in await session.scalars(
            select(SessionMessage).where(SessionMessage.user_id == user_id).order_by(SessionMessage.id_)
        ):
            await session.delete(message)
        await session.commit()


async def group_message(event: Event) -> bool:
    return event.get_user_id() != event.get_session_id()


async def enabled_group(
    event: Event, session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()
) -> bool:
    return bool(
        (await group_message(event))
        and (g := await session.get(ChatGroup, {"group_id": group_id}))
        and g.enabled
        and user_id not in json.loads(g.blocked_user)
    )
#
#
# def find_image_cache(image: bytes) -> Optional[str]:
#     if (img_hash := hashlib.sha256(image).hexdigest()) in cached_images:
#         return cached_images[img_hash][0]
#     return None
#
#
# def update_image_cache(image: bytes, summary: str):
#     dt = datetime.now()
#     cached_images[hashlib.sha256(image).hexdigest()] = summary, dt
#     for key, data in copy.deepcopy(cached_images):
#         if (data[1] - dt).total_seconds() > 10000:


async def get_image_summary(segment: Image, event: Event, bot: Bot, state: T_State) -> str:
    if not isinstance(image := await image_fetch(event, bot, state, segment), bytes):
        return "暂无信息"
    img_hash = hashlib.sha256(image).hexdigest()
    if (cache := await image_cache.get(img_hash)) is not None:
        return cache
    image_base64 = base64.b64encode(image).decode("utf-8")
    messages = [
        generate_message(await lang.text("prompt_group.image_describe_system", event.get_user_id()), "system"),
        generate_message(
            [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": await lang.text("prompt_group.image_describe_user", event.get_user_id())},
            ],
            "user",
        ),
    ]

    try:
        summary = (
            await fetch_message(messages, model="google/gemini-2.5-flash", extra_headers={
                "X-Title": "Moonlark - Image Describe",
                "HTTP-Referer": "https://image.moonlark.itcdt.top",
            })
        ).strip()
        await image_cache.set(img_hash, summary)
        return summary
    except Exception:
        logger.warning(traceback.format_exc())
        return "暂无信息"


async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State) -> str:
    str_msg = ""
    for segment in message:
        if isinstance(segment, Text):
            str_msg += segment.text
        elif isinstance(segment, At):
            user = await get_user(segment.target)
            if (not user.has_nickname()) and (user_info := await get_user_info(bot, event, segment.target)):
                nickname = user_info.user_displayname or user_info.user_name
            else:
                nickname = user.get_nickname()
            str_msg += f"@{nickname}"
        elif isinstance(segment, Image):
            str_msg += f"[图片: {await get_image_summary(segment, event, bot, state)}]"
        elif isinstance(segment, Reply) and segment.msg is not None:
            if isinstance(segment.msg, UniMessage):
                str_msg += f"[回复: {await parse_message_to_string(segment.msg, event, bot, state)}]"
            else:
                str_msg += f"[回复: {segment.msg}]"
    return str_msg
