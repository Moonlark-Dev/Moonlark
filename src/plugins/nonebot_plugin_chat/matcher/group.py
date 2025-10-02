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
import json
import random
import re
import asyncio
from datetime import datetime, timedelta
from nonebot.adapters.qq import Bot as BotQQ
from nonebot.params import CommandArg
from nonebot.typing import T_State
from typing import TypedDict, Optional, Any
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_alconna import UniMessage, Target, get_target
from nonebot_plugin_chat.utils.note_manager import get_context_notes
from nonebot_plugin_chat.utils.tools.note import get_note_poster
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

from nonebot_plugin_larkuser import get_user
from nonebot import on_message, on_command
from nonebot.adapters import Event, Bot, Message
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session, get_session
from nonebot.log import logger
from nonebot_plugin_openai import generate_message
from nonebot_plugin_openai.types import Messages, Message as OpenAIMessage, AsyncFunction, FunctionParameter
from nonebot_plugin_openai.utils.chat import MessageFetcher
from nonebot.matcher import Matcher

from ..utils.memory_activator import activate_memories_from_text
from ..lang import lang
from ..utils.memory_graph import cleanup_old_memories
from ..models import ChatGroup
from ..utils import enabled_group, parse_message_to_string, splitter
from ..utils.tools import browse_webpage, search_on_google, describe_image, request_wolfram_alpha

BASE_DESIRE = 30


class CachedMessage(TypedDict):
    content: str
    nickname: str
    user_id: str
    send_time: datetime
    self: bool
    message_id: str


def generate_message_string(message: CachedMessage) -> str:
    return f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]: {message['content']}\n"


def get_role(message: OpenAIMessage) -> str:
    if isinstance(message, dict):
        role = message["role"]
    else:
        role = message.role
    return role


def parse_reply(message: UniMessage, reply_message_id: Optional[str] = None) -> UniMessage:
    if reply_message_id:
        return message.reply(reply_message_id)
    return message


class MessageProcessor:

    def __init__(self, session: "GroupSession"):
        self.openai_messages: Messages = []
        self.session = session
        self.message_count = 0
        self.enabled = True
        self.cold_until = datetime.now()
        self.reply_message_ids = []
        self.blocked = False
        asyncio.create_task(self.loop())

    async def loop(self) -> None:
        while self.enabled:
            try:
                await self.get_message()
            except Exception as e:
                logger.exception(e)
                await asyncio.sleep(10)
            for _ in range(self.message_count - 10):
                await self.pop_first_message()

    async def get_message(self) -> None:
        if not self.session.message_queue:
            await asyncio.sleep(3)
            return
        message, event, state, user_id, nickname, dt, mentioned, message_id = self.session.message_queue.pop(0)
        text = await parse_message_to_string(message, event, self.session.bot, state)
        if not text:
            return
        msg_dict: CachedMessage = {
            "content": text,
            "nickname": nickname,
            "send_time": dt,
            "user_id": user_id,
            "self": False,
            "message_id": message_id,
        }
        await self.process_messages(msg_dict)
        self.session.cached_messages.append(msg_dict)
        if (mentioned or not self.session.message_queue) and not self.blocked:
            await self.generate_reply(mentioned)
            self.cold_until = datetime.now() + timedelta(seconds=5)

    def clean_special_message(self) -> None:
        while True:
            role = get_role(self.openai_messages[0])
            if role in ["user", "assistant"]:
                break
            self.openai_messages.pop(0)

    async def pop_first_message(self) -> None:
        self.clean_special_message()
        if len(self.openai_messages) == 0:
            return
        role = get_role(self.openai_messages[0])
        if role == "assistant":
            self.openai_messages.pop(0)
        elif role == "user":
            content = self.openai_messages[0]["content"]
            if next_message_pos := content.find("\n[") + 1:
                self.openai_messages[0]["content"] = content[next_message_pos:]
            else:
                self.openai_messages.pop(0)
            self.reply_message_ids.pop(0)
        self.message_count -= 1

    async def update_system_message(self) -> None:
        if (
            len(self.openai_messages) >= 1
            and isinstance(self.openai_messages[0], dict)
            and self.openai_messages[0]["role"] == "system"
        ):  # 这里不会出现非 dict 还是 role=system 的情况
            self.openai_messages[0] = await self.generate_system_prompt()
        else:
            self.openai_messages.insert(0, await self.generate_system_prompt())

    async def handle_group_cold(self, time_d: timedelta) -> None:
        min_str = time_d.total_seconds() // 60
        if len(self.openai_messages) > 0:
            return
        if isinstance(self.openai_messages[-1], dict) and self.openai_messages[-1]["role"] == "user":
            self.openai_messages[
                -1
            ].content += f"\n[{datetime.now().strftime('%H:%M:%S')}]: 当前群聊已经冷群了 {min_str} 分钟。"
        elif (not isinstance(self.openai_messages[-1], dict)) and self.openai_messages[-1].role == "assistant":
            self.openai_messages.append(
                generate_message(
                    content=f"[{datetime.now().strftime('%H:%M:%S')}]: 当前群聊已经冷群了 {min_str} 分钟。", role="user"
                )
            )
        else:
            return
        if not self.blocked:
            await self.generate_reply()
            self.blocked = True  # 再次收到消息后才会解锁

    async def generate_reply(self, ignore_desire: bool = False) -> None:
        logger.debug(desire := self.session.desire * 0.0075)
        if self.cold_until > datetime.now() and not (ignore_desire or random.random() <= desire):
            return
        elif len(self.openai_messages) <= 0 or (
            (not isinstance(self.openai_messages[-1], dict))
            and self.openai_messages[-1].role in ["system", "assistant"]
        ):
            return
        await self.update_system_message()
        fetcher = MessageFetcher(
            self.openai_messages,
            False,
            functions=[
                AsyncFunction(
                    func=browse_webpage,
                    description="使用浏览器访问指定 URL 并获取网页内容的 Markdown 格式文本",
                    parameters={
                        "url": FunctionParameter(type="string", description="要访问的网页的 URL 地址", required=True)
                    },
                ),
                AsyncFunction(
                    func=search_on_google,
                    description="使用Google搜索信息",
                    parameters={
                        "keyword": FunctionParameter(
                            type="string",
                            description="搜索关键词。请使用简洁的关键词而非完整句子。将用户问题转换为2-5个相关的关键词，用空格分隔。例如：'人工智能 发展 趋势' 而不是 '人工智能的发展趋势是什么'",
                            required=True,
                        )
                    },
                ),
                AsyncFunction(
                    func=describe_image,
                    description="获取一张网络图片的内容的描述。",
                    parameters={
                        "image_url": FunctionParameter(type="string", description="目标图片的 URL 地址", required=True)
                    },
                ),
                AsyncFunction(
                    func=request_wolfram_alpha,
                    description="调用 Wolfram|Alpha 进行计算。",
                    parameters={
                        "question": FunctionParameter(
                            type="string",
                            description="输入 Wolfram|Alpha 的内容，形式可以是数学表达式、Wolfram Language、LaTeX 或自然语言",
                            required=True,
                        )
                    },
                ),
                AsyncFunction(
                    func=get_note_poster(self.session.group_id),
                    description="添加一段笔记到你的笔记本中。",
                    parameters={
                        "text": FunctionParameter(
                            type="string",
                            description="要添加的笔记内容。",
                            required=True,
                        ),
                        "expire_days": FunctionParameter(
                            type="integer",
                            description="笔记的过期天数。如果未指定，则默认为 7 天。",
                            required=False,
                        ),
                        "keywords": FunctionParameter(
                            type="string",
                            description="笔记的关键词，用于搜索。如果未指定，则默认为空。",
                            required=False,
                        )
                    }
                )
            ],
            identify="Chat",
            pre_function_call=self.send_function_call_feedback,
        )
        async for message in fetcher.fetch_message_stream():
            self.message_count += 1
            await self.send_reply_text(message)
        self.openai_messages = fetcher.get_messages()

    def get_reply_message_id(self, text: str) -> tuple[str, Optional[str]]:
        reply_message_id = None
        while m := re.search(r"\{REPLY:\d+}", text):
            try:
                reply_message_id = self.reply_message_ids[-int(m[0][7:-1])]
            except IndexError:
                continue
            text = text.replace(m[0], "")
            break
        return text, reply_message_id

    async def send_function_call_feedback(
        self, call_id: str, name: str, param: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        match name:
            case "browse_webpage":
                await UniMessage().text(
                    text=await lang.text("tools.browse", self.session.user_id, param.get("url"))
                ).send(target=self.session.target, bot=self.session.bot)
            case "request_wolfram_alpha":
                await UniMessage().text(
                    text=await lang.text("tools.wolfram", self.session.user_id, param.get("question"))
                ).send(target=self.session.target, bot=self.session.bot)
            case "search_on_google":
                await UniMessage().text(
                    text=await lang.text("tools.google", self.session.user_id, param.get("keyword"))
                ).send(target=self.session.target, bot=self.session.bot)
        return call_id, name, param

    async def send_text(self, reply_text: str) -> None:
        reply_text, reply_message_id = self.get_reply_message_id(reply_text)
        await parse_reply(self.session.format_message(reply_text), reply_message_id).send(
            target=self.session.target, bot=self.session.bot
        )

    async def send_reply_text(self, reply_text: str) -> None:
        for msg in splitter.split_message(reply_text):
            for line in msg.splitlines():
                if line.startswith(".skip"):
                    return
                elif line.startswith(".leave"):
                    await self.session.mute()
                    return
            if msg:
                await self.send_text(msg)

    async def process_messages(self, msg_dict: CachedMessage) -> None:
        if (
            len(self.openai_messages) <= 0
            or (not isinstance(self.openai_messages[-1], dict))
            or self.openai_messages[-1]["role"] != "user"
        ):
            self.openai_messages.append(generate_message(generate_message_string(msg_dict), "user"))
        else:
            self.openai_messages[-1]["content"] += generate_message_string(msg_dict)
        self.message_count += 1
        self.reply_message_ids.append(msg_dict["message_id"])
        logger.debug(self.openai_messages)
        async with get_session() as session:
            r = await session.get(ChatGroup, {"group_id": self.session.group_id})
            self.blocked = r and msg_dict["user_id"] in json.loads(r.blocked_user)

    def get_message_content_list(self) -> list[str]:
        l = []
        for msg in self.openai_messages:
            if isinstance(msg, dict) and "content" in msg:
                l.append(msg["content"])
            elif hasattr(msg, "content"):
                l.append(msg.content)  # pyright: ignore[reportAttributeAccessIssue]
        return l

    async def generate_system_prompt(self) -> OpenAIMessage:

        # 获取最近几条缓存消息作为上下文
        recent_messages = self.session.cached_messages[-5:] if self.session.cached_messages else []
        recent_context = " ".join([msg["content"] for msg in recent_messages])

        # 激活相关记忆
        chat_history = "\n".join(self.get_message_content_list())
        activated_memories = await activate_memories_from_text(
            context_id=self.session.group_id,
            target_message=recent_context,
            max_memories=5,
            chat_history=chat_history
        )

        # 获取相关笔记
        note_manager = await get_context_notes(self.session.group_id)
        notes = await note_manager.filter_note(chat_history, [m[0] for m in activated_memories])

        # 构建记忆文本
        memory_text_parts = []

        if activated_memories:
            for concept, memory_content in activated_memories:
                memory_text_parts.append(f"- {concept}: {memory_content}")

        # 添加笔记到记忆文本
        if notes:
            for note in notes:
                memory_text_parts.append(f"- {note.content}")

        final_memory_text = "\n".join(memory_text_parts) if memory_text_parts else "暂无"

        return generate_message(
            await lang.text(
                "prompt_group.default",
                self.session.user_id,
                final_memory_text,
                datetime.now().isoformat(),
            ),
            "system",
        )


from nonebot_plugin_alconna import get_message_id


class GroupSession:

    def __init__(self, group_id: str, bot: Bot, target: Target, lang_name: str = "zh_hans") -> None:
        self.group_id = group_id
        self.target = target
        self.bot = bot
        self.user_id = f"mlsid::--lang={lang_name}"
        self.message_queue: list[tuple[UniMessage, Event, T_State, str, str, datetime, bool, str]] = []
        self.cached_messages: list[CachedMessage] = []
        self.desire = BASE_DESIRE
        self.last_reward_participation: Optional[datetime] = None
        self.mute_until: Optional[datetime] = None
        self.memory_lock = False
        self.message_counter: dict[datetime, int] = {}
        self.user_counter: dict[datetime, set[str]] = {}
        self.processor = MessageProcessor(self)

    async def mute(self) -> None:
        self.mute_until = datetime.now() + timedelta(minutes=15)
        asyncio.create_task(self.update_memory())

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

    async def handle_message(
        self, message: UniMessage, user_id: str, event: Event, state: T_State, nickname: str, mentioned: bool = False
    ) -> None:
        message_id = get_message_id(event)
        self.message_queue.append((message, event, state, user_id, nickname, datetime.now(), mentioned, message_id))
        self.update_counters(user_id)
        await self.calculate_desire_on_message(mentioned)
        if len(self.cached_messages) >= 20:
            await self.update_memory()

    async def update_memory(self) -> None:
        if self.memory_lock or not self.cached_messages:
            return
        self.memory_lock = True
        try:
            await self.generate_memory()
        except Exception as e:
            logger.exception(e)
        self.memory_lock = False

    async def generate_memory(self) -> None:
        from ..utils.memory_graph import MemoryGraph

        messages = ""
        cached_messages = copy.deepcopy(self.cached_messages)
        for message in cached_messages:
            if message["self"]:
                messages += f'[{message["send_time"].strftime("%H:%M")}][Moonlark]: {message["content"]}\n'
            else:
                messages += f"[{message['send_time'].strftime('%H:%M')}][{message['nickname']}]: {message['content']}\n"

        # 使用新的记忆图系统
        memory_graph = MemoryGraph(self.group_id)
        await memory_graph.load_from_db()

        # 从消息历史构建记忆
        await memory_graph.build_memory_from_text(messages, compress_rate=0.15)

        # 保存记忆图到数据库
        await memory_graph.save_to_db()

        self.last_reward_participation = None
        self.cached_messages.clear()

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
            participation_boost = -20
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
        if self.processor.blocked or not self.cached_messages:
            return
        time_to_last_message = (dt - self.cached_messages[-1]["send_time"]).total_seconds()
        if time_to_last_message > 180:
            if random.random() <= self.desire / 100 and not self.cached_messages[-1]["self"]:
                await self.processor.generate_reply()


from ..config import config

groups: dict[str, GroupSession] = {}
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
        groups[session_id] = GroupSession(session_id, bot, get_target(event))
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
    await groups[session_id].handle_message(message, user_id, event, state, nickname, event.is_tome())


async def group_disable(group_id: str) -> None:
    if group_id in groups:
        group = groups.pop(group_id)
        group.processor.enabled = False
        await group.update_memory()


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
                await group_disable(group_id)
                await lang.send("command.switch.disabled", user_id)
        case "off":
            g = ChatGroup(group_id=group_id, enabled=False)
            await group_disable(group_id)
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
                # 清理图形记忆
                

                await cleanup_old_memories(group_id, forget_ratio=1.0)  # 清除所有记忆
                await lang.send("command.done", user_id)
            else:
                await lang.send("command.disabled", user_id)
        case "cleanup-memory":
            if g is not None:
                

                forgotten_count = await cleanup_old_memories(group_id, forget_ratio=0.3)
                await lang.send("command.memory.clean", user_id, forgotten_count)
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


@scheduler.scheduled_job("cron", hour="3", id="cleanup_expired_notes")
async def _() -> None:
    """Daily cleanup of expired notes at 3 AM"""
    from ..utils.note_manager import cleanup_expired_notes
    deleted_count = await cleanup_expired_notes()
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} expired notes")
