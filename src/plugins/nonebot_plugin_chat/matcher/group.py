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
import copy
import random
import re
import asyncio
from datetime import datetime, timedelta
from nonebot.adapters.qq import Bot as BotQQ
from nonebot.params import CommandArg
from nonebot.typing import T_State
from typing import TypedDict, Optional
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_alconna import UniMessage, Target, get_target
from nonebot_plugin_userinfo import EventUserInfo, UserInfo
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
from ..utils import enabled_group, parse_message_to_string

BASE_DESIRE = 30


class CachedMessage(TypedDict):
    content: str
    nickname: str
    user_id: str
    send_time: datetime
    self: bool


class Group:

    def __init__(
        self, group_id: str, cached_user_id: str, bot: Bot, target: Target, lang_name: str = "zh_hans"
    ) -> None:
        self.group_id = group_id
        self.target = target
        self.cached_user_id = cached_user_id
        self.bot = bot
        self.user_id = f"mlsid::--lang={lang_name}"
        self.cached_messages: list[CachedMessage] = []
        self.desire = BASE_DESIRE
        self.triggered = False
        self.last_reward_participation: Optional[datetime] = None
        self.mute_until: Optional[datetime] = None
        self.memory_lock = False
        self.message_counter: dict[datetime, int] = {}
        self.user_counter: dict[datetime, set[str]] = {}

    async def mute(self) -> None:
        self.mute_until = datetime.now() + timedelta(minutes=15)
        asyncio.create_task(self.generate_memory(self.cached_user_id))

    def update_counters(self, user_id: str) -> None:
        dt = datetime.now().replace(second=0, microsecond=0)
        if dt in self.user_counter:
            self.user_counter[dt].add(user_id)
        else:
            self.user_counter[dt] = {user_id}
        self.message_counter[dt] = self.message_counter.get(dt, 0) + 1

    def get_counters(self) -> tuple[int, int]:
        msg_count_removable_keys = []
        dt = datetime.now()
        message_count = 0
        for key, value in self.message_counter.items():
            if (dt - key) > timedelta(minutes=10):
                msg_count_removable_keys.append(key)
            else:
                message_count += value
        user_count_removable_keys = []
        user_count = 0
        for key, value in self.user_counter.items():
            if (dt - key) > timedelta(minutes=10):
                user_count_removable_keys.append(key)
            else:
                user_count += len(value)
        # remove removable keys
        for key in msg_count_removable_keys:
            self.message_counter.pop(key)
        for key in user_count_removable_keys:
            self.user_counter.pop(key)
        return message_count, user_count

    async def process_message(
        self, message: UniMessage, user_id: str, event: Event, state: T_State, nickname: str, mentioned: bool = False
    ) -> None:
        msg = await parse_message_to_string(message, event, self.bot, state)
        if not msg:
            return
        msg_dict: CachedMessage = {
            "content": msg,
            "nickname": nickname,
            "send_time": datetime.now(),
            "user_id": user_id,
            "self": False,
        }
        self.cached_messages.append(msg_dict)
        self.update_counters(user_id)
        await self.calculate_desire_on_message(mentioned)
        logger.debug(self.desire)
        if mentioned:
            await self.handle_mention(user_id)
            return
        await asyncio.sleep(3)
        if self.triggered or self.cached_messages[-1] is not msg_dict:
            return
        elif random.random() <= self.desire / 100:
            self.triggered = True
            await self.reply(user_id)
            await asyncio.sleep(round(self.desire / 100 * 2.5))
            self.triggered = False
        elif len(self.cached_messages) >= 15:
            asyncio.create_task(self.generate_memory(user_id))

    async def handle_mention(self, user_id: str) -> None:
        self.triggered = True
        await self.reply(user_id)
        self.triggered = False

    async def generate_memory(self, user_id: str, clean_all: bool = False) -> None:
        messages = ""
        if self.memory_lock or not self.cached_messages:
            return
        self.memory_lock = True
        if len(self.cached_messages) >= 15 and not clean_all:
            cached_messages = copy.deepcopy(self.cached_messages[:10])
        else:
            cached_messages = copy.deepcopy(self.cached_messages)
        for message in cached_messages:
            if message["self"]:
                messages += f'[{message["send_time"].strftime("%H:%M")}][Moonlark]: {message["content"]}\n'
            else:
                messages += f"[{message['send_time'].strftime('%H:%M')}][{message['nickname']}]: {message['content']}\n"
        memory = await fetch_messages(
            [
                generate_message(await lang.text("prompt_group.memory", self.user_id), "system"),
                generate_message(
                    await lang.text("prompt_group.memory_2", self.user_id, await self.get_memory(), messages), "user"
                ),
            ],
            user_id,
            model="moonshotai/kimi-k2:free",
            extra_headers={"X-Title": "Moonlark - Memory", "HTTP-Referer": "https://memory.moonlark.itcdt.top"},
        )
        async with get_session() as session:
            g = await session.get_one(ChatGroup, {"group_id": self.group_id})
            g.memory = memory
            await session.commit()
        self.last_reward_participation = None
        # remove cached messages
        self.cached_messages = self.cached_messages[len(cached_messages) :]
        self.memory_lock = False

    async def get_messages(self) -> Messages:
        messages = [
            generate_message(
                await lang.text(
                    "prompt_group.default", self.user_id, await self.get_memory(), datetime.now().isoformat()
                ),
                "system",
            ),
            generate_message("", "user"),
        ]
        for message in self.cached_messages:
            if message["self"]:
                messages.append(generate_message(message["content"], "assistant"))
                messages.append(generate_message("", "user"))
            else:
                messages[-1][
                    "content"
                ] += f"[{message['send_time'].strftime('%H:%M')}][{message['nickname']}]: {message['content']}\n"
        return messages

    async def reply(self, user_id: str) -> bool:
        messages = await self.get_messages()
        reply = await fetch_messages(
            messages,
            user_id,
            extra_headers={"X-Title": "Moonlark - Chat", "HTTP-Referer": "https://chat.moonlark.itcdt.top"},
        )
        is_first_message = True
        for line in reply.splitlines():
            if line == ".skip":
                return False
            elif line.startswith("("):
                continue
            elif line:
                if is_first_message:
                    is_first_message = False
                else:
                    await asyncio.sleep(len(line.strip()) * 0.07)
                await self.format_message(line).send(target=self.target, bot=self.bot)
            else:
                await asyncio.sleep(1)
        self.cached_messages.append(
            {
                "content": reply,
                "self": True,
                "send_time": datetime.now(),
                # NOTE Not important
                "nickname": "",
                "user_id": "",
            }
        )
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
        processing_at = False
        for char in message:
            if char == "@":
                uni_msg[-1].text += segment
                segment = "@"
                processing_at = True
            elif segment:
                segment += char
                if segment[1:] in users and processing_at:
                    user_id = users[segment[1:]]
                    uni_msg = uni_msg.at(user_id=user_id).text(text="")
                    segment = ""
                    processing_at = False
            else:
                uni_msg[-1].text += char
        uni_msg[-1].text += segment
        return uni_msg

    def get_users(self) -> dict[str, str]:
        users = {}
        for message in self.cached_messages:
            if not message["self"]:
                users[message["nickname"]] = message["user_id"]
        return users

    def calculate_desire_on_timer(self) -> None:
        msg_count, user_msg_count = self.get_counters()
        loneliness_boost = 10 if (msg_count >= 3 and user_msg_count <= 2) else 0
        activity_penalty = 10 - min(30.0, 0.3 * msg_count)
        self.desire = self.desire + activity_penalty + loneliness_boost

    async def calculate_desire_on_message(self, mentioned: bool = False) -> None:
        dt = datetime.now()
        cached_messages = [m for m in self.cached_messages if (dt - m["send_time"]).total_seconds() <= 600]
        msg_count = self.get_counters()[0]
        base = self.desire * 0.8 + BASE_DESIRE * 0.2
        mention_boost = 30 if mentioned else 0
        bot_participate = False
        for msg in cached_messages:
            if msg["self"]:
                bot_participate = True
        activity_penalty = min(30.0, 0.1 * msg_count)
        if bot_participate and self.is_participation_boost_available():
            participation_boost = -10
            self.last_reward_participation = datetime.now()
        else:
            participation_boost = 0
        new_desire = base + mention_boost + participation_boost - activity_penalty
        self.desire = max(0.0, min(100.0, new_desire))

    def is_participation_boost_available(self) -> bool:
        if self.last_reward_participation is None:
            return True
        dt = datetime.now()
        return (dt - self.last_reward_participation).total_seconds() >= 180

    async def process_timer(self) -> None:
        dt = datetime.now()
        self.calculate_desire_on_timer()
        if self.mute_until and dt > self.mute_until:
            self.mute_until = None
        if not self.cached_messages:
            return
        time_to_last_message = (dt - self.cached_messages[-1]["send_time"]).total_seconds()
        if time_to_last_message > 300:
            if random.random() <= self.desire / 100 and not self.cached_messages[-1]["self"]:
                await self.reply(self.cached_user_id)
            await self.generate_memory(self.cached_user_id, True)


from ..config import config

groups: dict[str, Group] = {}
matcher = on_message(priority=50, rule=enabled_group, block=False)


@matcher.handle()
async def _(
    event: Event,
    bot: Bot,
    state: T_State,
    user_info: UserInfo = EventUserInfo(),
    user_id: str = get_user_id(),
    session_id: str = get_group_id(),
) -> None:
    if isinstance(bot, BotQQ):
        await matcher.finish()
    elif session_id not in groups:
        groups[session_id] = Group(session_id, user_id, bot, get_target(event))
    elif groups[session_id].mute_until is not None:
        await matcher.finish()
    plaintext = event.get_plaintext().strip()
    if any([plaintext.startswith(p) for p in config.command_start]):
        await matcher.finish()
    platform_message = event.get_message()
    message = await UniMessage.of(message=platform_message, bot=bot).attach_reply(event, bot)
    user = await get_user(user_id)
    if user.has_nickname():
        nickname = user.get_nickname()
    else:
        nickname = user_info.user_displayname or user_info.user_name
    await groups[session_id].process_message(message, user_id, event, state, nickname, event.is_tome())


async def group_disable(group_id: str, user_id: str) -> None:
    if group_id in groups:
        group = groups.pop(group_id)
        await group.generate_memory(user_id)


@on_command("chat").handle()
async def _(
    matcher: Matcher,
    bot: Bot,
    session: async_scoped_session,
    message: Message = CommandArg(),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    if isinstance(bot, BotQQ):
        await lang.finish("command.not_available", user_id)
    argv = message.extract_plain_text().split(" ")
    g = await session.get(ChatGroup, {"group_id": group_id})
    if len(argv) == 0:
        await lang.finish("command.no_argv", user_id)
    match argv[0]:
        case "switch":
            if g is None or not g.enabled:
                g = ChatGroup(group_id=group_id, enabled=True)
                await lang.send("command.switch.enabled", user_id)
            else:
                g.enabled = False
                await group_disable(group_id, user_id)
                await lang.send("command.switch.disabled", user_id)
        case "off":
            g = ChatGroup(group_id=group_id, enabled=False)
            await group_disable(group_id, user_id)
            await lang.send("command.switch.disabled", user_id)
        case "on":
            g = ChatGroup(group_id=group_id, enabled=True)
            await lang.send("command.switch.enabled", user_id)
        case "desire":
            if len(argv) > 1 and re.match(r"^\d+\.?\d*$", argv[1]) and group_id in groups:
                groups[group_id].desire = float(argv[1])
                await lang.send("command.desire.set", user_id)
            elif group_id in groups:
                await lang.send("command.desire.get", user_id, groups[group_id].desire)
            elif g and g.enabled:
                await lang.send("command.not_inited", user_id)
            else:
                await lang.send("command.disabled", user_id)
        case "mute":
            if group_id in groups:
                await lang.send("command.mute", user_id)
                await groups[group_id].mute()
            elif g and g.enabled:
                await lang.send("command.not_inited", user_id)
            else:
                await lang.send("command.disabled", user_id)
        case "unmute":
            if group_id in groups:
                groups[group_id].mute_until = None
                await lang.send("command.unmute", user_id)
            elif g and g.enabled:
                await lang.send("command.not_inited", user_id)
            else:
                await lang.send("command.disabled", user_id)
        case "reset-memory":
            if g is not None:
                g.memory = ""
                await lang.send("command.done", user_id)
            else:
                await lang.send("command.disabled", user_id)
        case _:
            await lang.finish("command.no_argv", user_id)
    await session.merge(g)
    await session.commit()
    await matcher.finish()


@scheduler.scheduled_job("cron", minute="*", id="trigger_group")
async def _() -> None:
    for group in groups.values():
        await group.process_timer()
