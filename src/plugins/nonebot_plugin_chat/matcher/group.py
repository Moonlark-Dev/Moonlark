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

import json
import random
import asyncio
from datetime import datetime
from nonebot.typing import T_State
from typing import TypedDict, NoReturn, Optional
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_alconna import UniMessage, Text, At, Image, Target, get_target, image_fetch, Reply
from nonebot_plugin_larkuser import get_user
from nonebot import on_message, on_command
from nonebot.adapters import Event, Bot, Message
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session, get_session
from nonebot.log import logger
from nonebot_plugin_openai import generate_message, fetch_messages
from nonebot_plugin_openai.types import Messages
from nonebot_plugin_chat.models import ChatGroup
from nonebot.matcher import Matcher
from ..lang import lang

BASE_DESIRE = 35



async def group_message(event: Event) -> bool:
    return event.get_user_id() != event.get_session_id()

async def enabled_group(event: Event, session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()) -> bool:
    return bool((await group_message(event)) and (g := await session.get(ChatGroup, {"group_id": group_id})) and g.enabled and user_id not in json.loads(g.blocked_user))



class CachedMessage(TypedDict):
    content: str
    nickname: str
    user_id: str
    send_time: datetime
    self: bool


async def get_image_summary(segment: Image, event: Event, bot: Bot, state: T_State) -> str:
    if not isinstance(image := await image_fetch(event, bot ,state, segment), bytes):
        return "暂无信息"
    return "暂无信息"


async def parse_message_to_string(message: UniMessage, event: Event, bot: Bot, state: T_State) -> str:
    str_msg = ""
    for segment in message:
        if isinstance(segment, Text):
            str_msg += segment.text
        elif isinstance(segment, At):
            str_msg += f" @{(await get_user(segment.target)).get_nickname()} "
        elif isinstance(segment, Image):
            str_msg += f"[图片: {await get_image_summary(segment, event, bot, state)}]"
    return str_msg


class Group:

    def __init__(self, group_id: str, cached_user_id: str, bot: Bot, target: Target, lang_name: str = "zh_hans") -> None:
        self.group_id = group_id
        self.target = target
        self.cached_user_id = cached_user_id
        self.bot = bot
        self.user_id = f"mlsid::--lang={lang_name}"
        self.cached_messages: list[CachedMessage] = []
        self.desire = BASE_DESIRE
        self.triggered = False
        self.last_reward_participation: Optional[datetime] = None

    async def process_message(self, message: UniMessage, user_id: str, event: Event, state: T_State, nickname: str, mentioned: bool = False) -> NoReturn:
        msg = await parse_message_to_string(message, event, self.bot, state)
        if not msg:
            return
        self.cached_messages.append({
            "content": msg,
            "nickname": nickname,
            "send_time": datetime.now(),
            "user_id": user_id,
            "self": False
        })
        await self.calculate_desire(mentioned)
        
        logger.debug(self.desire)
        if mentioned or (random.random() <= self.desire / 100 and msg != "[图片: 暂无信息]" and not self.triggered):
            self.triggered = True
            await self.reply(user_id)
            await asyncio.sleep(round(self.desire / 100 * 2.5))
            self.triggered = False
        elif len(self.cached_messages) >= 100 and not self.is_participation_boost_available():
            await self.generate_memory(user_id)
            self.cached_messages.clear()

            
    async def generate_memory(self, user_id: str) -> None:
        messages = ""
        if not self.cached_messages:
            return
        for message in self.cached_messages:
            if message["self"]:
                messages += f'[{message["send_time"].strftime("%H:%M")}][Moonlark]: {message["content"]}\n'
            else:
                messages += f"[{message['send_time'].strftime('%H:%M')}][{message['nickname']}]: {message['content']}\n"
        memory = await fetch_messages(
            [
                generate_message(await lang.text("prompt_group.memory", self.user_id), "system"),
                generate_message(await lang.text("prompt_group.memory_2", self.user_id, await self.get_memory(), messages), "user")
            ],
            user_id,
            model="deepseek/deepseek-r1-0528:free",
            extra_headers={"X-Title": "Moonlark - Memory", "HTTP-Referer": "https://memory.moonlark.itcdt.top"}
        )
        async with get_session() as session:
            g = await session.get_one(ChatGroup, {"group_id": self.group_id})
            g.memory = memory
            await session.commit()
        self.last_reward_participation = None

    async def get_messages(self) -> Messages:
        messages = [
            generate_message(await lang.text("prompt_group.default", self.user_id, await self.get_memory(), datetime.now().isoformat()), "system"),
            generate_message("", "user")
        ]
        for message in self.cached_messages:
            if message["self"]:
                messages.append(generate_message(message["content"], "assistant"))
                messages.append(generate_message("", "user"))
            else:
                messages[-1]["content"] += f"[{message['send_time'].strftime('%H:%M')}][{message['nickname']}]: {message['content']}\n"
        return messages

    async def reply(self, user_id: str) -> bool:
        messages = await self.get_messages()
        reply = await fetch_messages(messages, user_id, extra_headers={"X-Title": "Moonlark - Chat", "HTTP-Referer": "https://chat.moonlark.itcdt.top"})
        for line in reply.splitlines():
            if line == ".skip":
                return False
            elif line:
                await asyncio.sleep(len(line) * 0.02)
                await self.format_message(line).send(target=self.target, bot=self.bot)
        self.cached_messages.append({
            "content": reply,
            "self": True,
            "send_time": datetime.now(),

            # NOTE Not important
            "nickname": "",
            "user_id": "",
        })
        return True

    async def get_memory(self) -> str:
        async with get_session() as session:
            g = await session.get_one(ChatGroup, {"group_id": self.group_id})
            return str(g.memory)

    def format_message(self, origin_message: str) -> UniMessage:
        if "[Moonlark]:" in origin_message:
            message = "[Moonlark]:".join(origin_message.split("[Moonlark]:", 1)[1:])
        elif "Moonlark:" in origin_message:
            message = "[Moonlark]:".join(origin_message.split("Moonlark:", 1)[1:])
        else:
            message = origin_message
        message = message.strip()
        users = self.get_users()
        uni_msg = UniMessage().text(text="")
        segment = ""
        for char in message:
            if char == "@":
                uni_msg[-1].text += segment
                segment = "@"
            elif segment:
                segment += char
                if segment[1:] in users:
                    user_id = users[segment[1:]]
                    uni_msg = uni_msg.at(user_id=user_id).text(text="")
                    segment = ""
            else:
                uni_msg[-1].text += char
        return uni_msg



    def get_users(self) -> dict[str, str]:
        users = {}
        for message in self.cached_messages:
            if not message["self"]:
                users[message["nickname"]] = message["user_id"]
        return users

    async def calculate_desire(self, mentioned: bool = False) -> None:
        dt = datetime.now()
        cached_messages = [m for m in self.cached_messages if (dt - m["send_time"]).total_seconds() <= 600]
        msg_count = len(cached_messages)
        base = self.desire * 0.8 + BASE_DESIRE * 0.2
        mention_boost = 30 if mentioned else 0
        user_msg_count = {}
        bot_participate = False
        for msg in cached_messages:
            if not msg["self"]:
                if msg["user_id"] in user_msg_count:
                    user_msg_count[msg["user_id"]] += 1
                else:
                    user_msg_count[msg["user_id"]] = 1
            else:
                bot_participate = True
        activity_penalty = min(30.0, 0.3 * msg_count)
        loneliness_boost = 30 if (
            msg_count >= 3 and
            len(user_msg_count) == 1 and
            bot_participate and
            not mentioned
        ) else 0
        if bot_participate and self.is_participation_boost_available():
            participation_boost = -10
            self.last_reward_participation = datetime.now()
        else:
            participation_boost = 0
        new_desire = base + mention_boost + participation_boost - activity_penalty + loneliness_boost
        self.desire = max(0.0, min(100.0, new_desire))


    def is_participation_boost_available(self) -> bool:
        if self.last_reward_participation is None:
            return True
        dt = datetime.now()
        return (dt - self.last_reward_participation).total_seconds() >= 180


    async def process_timer(self) -> None:
        dt = datetime.now()
        if not self.cached_messages:
            return
        time_to_last_message = (dt - self.cached_messages[-1]["send_time"]).total_seconds()
        if time_to_last_message > 600 and random.random() <= (100 - self.desire) / 100 and not self.cached_messages[-1]["self"]:
            await self.reply(self.cached_user_id)
            await self.generate_memory(self.cached_user_id)
            self.cached_messages.clear()
            







groups: dict[str, Group] = {}

@on_message(priority=50, rule=enabled_group, block=True).handle()
async def _(event: Event, bot: Bot, state: T_State, user_id: str = get_user_id(), session_id: str = get_group_id()) -> None:
    if session_id not in groups:
        groups[session_id] = Group(session_id, user_id, bot, get_target(event))
    user = await get_user(user_id)
    message = UniMessage.generate_without_reply(message=event.get_message(), event=event)
    await groups[session_id].process_message(message, user_id, event, state, user.get_nickname(), event.is_tome())



@on_command("switch-chat").handle()
async def _(matcher: Matcher, session: async_scoped_session, group_id: str = get_group_id(), user_id: str = get_user_id()) -> None:
    g = await session.get(ChatGroup, {"group_id": group_id})
    if g is None:
        g = ChatGroup(group_id=group_id, enabled=True)
        await lang.send("switch.on", user_id)
    elif g.enabled:
        g.enabled = False
        await lang.send("switch.off", user_id)
    else:
        g.enabled = True
        await lang.send("switch.on", user_id)
    await session.merge(g)
    await session.commit()
    await matcher.finish()


@scheduler.scheduled_job("cron", minute="*", id="trigger_group")
async def _() -> None:
    for group in groups.values():
        await group.process_timer()

