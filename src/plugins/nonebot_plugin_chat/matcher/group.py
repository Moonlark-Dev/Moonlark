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
import re
from nonebot_plugin_alconna import get_message_id
import random
from openai.types.chat import ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
import asyncio
from datetime import datetime, timedelta
from nonebot.adapters.qq import Bot as BotQQ
from nonebot.params import CommandArg
from nonebot.typing import T_State
from typing import TypedDict, Optional, Any
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_alconna import UniMessage, Target, get_target
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
from ..utils.note_manager import get_context_notes
from ..utils.memory_graph import cleanup_old_memories
from ..models import ChatGroup
from ..utils import enabled_group, parse_message_to_string, splitter
from ..utils.interrupter import Interrupter
from ..utils.tools import (
    browse_webpage,
    web_search,
    describe_image,
    request_wolfram_alpha,
    get_fetcher,
    get_note_poster,
)

BASE_DESIRE = 30


class CachedMessage(TypedDict):
    content: str
    nickname: str
    user_id: str
    send_time: datetime
    self: bool
    message_id: str


def generate_message_string(message: CachedMessage) -> str:
    return f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]({message['message_id']}): {message['content']}\n"


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
        self.cached_activated_memories: list[tuple[str, str]] = []
        self.enabled = True
        self.interrupter = Interrupter(session)
        self.cold_until = datetime.now()
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
        self.interrupter.record_message()
        if await self.interrupter.should_interrupt(text, user_id):
            # 如果需要阻断，直接返回
            return
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
        first_msg = self.openai_messages[0]
        role = get_role(first_msg)
        if role == "assistant":
            self.openai_messages.pop(0)
        elif role == "user" and isinstance(first_msg, dict) and isinstance(content := first_msg.get("content"), str):
            if next_message_pos := content.find("\n[") + 1:
                first_msg["content"] = content[next_message_pos:]
            else:
                self.openai_messages.pop(0)
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
        delta_content = f"\n[{datetime.now().strftime('%H:%M:%S')}]: 当前群聊已经冷群了 {min_str} 分钟。"
        latest_message = self.openai_messages[-1]
        if isinstance(latest_message, dict):
            if get_role(latest_message) == "user":
                if (content := latest_message.get("content")) and isinstance(content, str):
                    latest_message["content"] = content + delta_content
                else:
                    latest_message["content"] = delta_content
            else:
                return

        elif latest_message.role == "assistant":
            self.openai_messages.append(generate_message(content=delta_content, role="user"))
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

        # 记录一次机器人响应
        self.interrupter.record_response()
        await self.update_system_message()
        fetcher = MessageFetcher(
            self.openai_messages,
            False,
            functions=[
                AsyncFunction(
                    func=get_fetcher(self.session.bot),
                    description=(
                        "获取合并转发消息的内容。\n"
                        "**何时必须调用**: 当聊天记录中出现形如 `[合并转发:...]` 的消息时。\n"
                        "**判断标准**: 只要看到 `[合并转发: {ID}]` 格式的文本，就**必须**调用此工具来获取其内部的具体消息。这是理解对话上下文的关键步骤。\n"
                        "**禁止行为**: 除非该工具报错，绝对禁止忽略合并转发消息或回复“咱看不到合并转发的内容喵”。"
                    ),
                    parameters={
                        "forward_id": FunctionParameter(
                            type="string",
                            description="转发消息的 ID，是“[合并转发: {一段数字ID}]”中间的“{一段数字}”，例如“[合并转发: 1234567890]”中的“1234567890”",
                            required=True,
                        ),
                    },
                ),
                AsyncFunction(
                    func=browse_webpage,
                    description=(
                        "使用浏览器访问指定 URL 并获取网页内容的 Markdown 格式文本。\n"
                        "**何时必须调用**:\n"
                        "1. 当用户直接提供一个 URL，或者要求你**总结、分析、提取特定网页的内容**时。\n"
                        "2. 当你使用 web_search 获取到了一些结果，需要详细查看某个网页获取更多的信息时。\n"
                        "**判断标准**: 只要输入中包含 `http://` 或 `https://`，并且用户的意图与该链接内容相关，就**必须**调用此工具。"
                    ),
                    parameters={
                        "url": FunctionParameter(type="string", description="要访问的网页的 URL 地址", required=True)
                    },
                ),
                AsyncFunction(
                    func=web_search,
                    description=(
                        "调用搜索引擎，从网络中搜索信息。\n"
                        "**何时必须调用**: 当被问及任何关于**时事新闻、近期事件、特定人物、产品、公司、地点、定义、统计数据**或任何你的知识库可能未覆盖的现代事实性信息时。\n"
                        "**判断标准**: 只要问题涉及“是什么”、“谁是”、“在哪里”、“最新的”、“...怎么样”等客观事实查询，就**必须**使用网络搜索。\n"
                    ),
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
                    description=(
                        "获取一张网络图片的内容描述。\n"
                        "**何时必须调用**: \n"
                        "1. 在 `browse_webpage` 工具中看到了一张图片时，实际上该工具获取到的图片会以 `![](图片URL)` 的形式展示）。\n"
                        "2. 用户发送了一个 **图片 URL**（如以 `.jpg`, `.png`, `.webp` 等结尾） 时。\n"
                        "消息中的 [图片: {描述}] 中的 {描述} 是用户发送的图片已经经过该工具处理结果，即用户发送的图片的描述， **它不是一个 URL，不能被填入这个工具！！！**"
                        "如果向这个工具传入的 URL 不对应一张图片的话，这个工具不会返回有效的内容。"
                    ),
                    parameters={
                        "image_url": FunctionParameter(
                            type="string",
                            description=(
                                "需要解释的图片的 URL 地址。\n"
                                "注意，该参数一定是一个完整的 URL 地址， **消息中的 [图片: {描述}] 中的 {描述} 部分不能被填入！**"
                            ),
                            required=True,
                        )
                    },
                ),
                AsyncFunction(
                    func=request_wolfram_alpha,
                    description=(
                        "调用 Wolfram|Alpha 进行计算。\n"
                        "**何时必须调用**: 当用户提出任何**数学计算（微积分、代数、方程求解等）、数据分析、单位换算、科学问题（物理、化学）、日期与时间计算**等需要精确计算和结构化数据的问题时。\n"
                        "**判断标准**: 如果问题看起来像一个数学题、物理公式或需要精确数据的查询，优先选择 Wolfram|Alpha 而不是网络搜索。例如：“2x^2+5x-3=0 的解是什么？”或“今天的日落时间是几点？”。\n"
                        "**禁止行为**: 不要尝试自己进行复杂的数学计算，这容易出错。"
                    ),
                    parameters={
                        "question": FunctionParameter(
                            type="string",
                            description=(
                                "输入 Wolfram|Alpha 的内容，形式可以是数学表达式、Wolfram Language、LaTeX 或自然语言。\n"
                                "使用自然语言提问时，使用英文以保证 Wolfram|Alpha 可以理解问题。"
                            ),
                            required=True,
                        )
                    },
                ),
                AsyncFunction(
                    func=get_note_poster(self.session.group_id),
                    description=(
                        "添加一段笔记到你的笔记本中。\n"
                        "**何时需要调用**: 当你认为某些信息对你理解群友或未来的互动非常重要时，可以自主选择使用它来记下。\n"
                        "**建议的使用场景 (完全由你判断！)**:\n"
                        "- 记下某位群友的**重要个人信息**，比如他们的生日、重要的纪念日、或提到的个人喜好（例如最喜欢的游戏、食物等），这样你可以在未来的对话中恰当地提及，显得更加体贴。\n"
                        "- 记录群聊中达成的**重要共识或约定**，例如大家约定好下次一起玩游戏的时间。\n"
                        "- 保存一些对你有用的**事实性知识**，特别是通过工具查询到的、并可能在未来对话中再次被提及的内容。\n"
                        " **使用提示**: 把你需要记住的核心信息整理成简洁的句子放进 `text` 参数里，这个工具的目的是帮助你更好地维系和群友的关系。"
                    ),
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
                        ),
                    },
                ),
            ],
            identify="Chat",
            pre_function_call=self.send_function_call_feedback,
            timeout_per_request=15,
            timeout_response=Choice(
                finish_reason="stop", message=ChatCompletionMessage(role="assistant", content=".skip"), index=0
            ),
        )
        async for message in fetcher.fetch_message_stream():
            self.message_count += 1
            await self.send_reply_text(message)
        self.openai_messages = fetcher.get_messages()
        if datetime.now() < self.interrupter.sleep_end_time:
            self.interrupter.sleep_end_time = datetime.min

    def get_reply_message_id(self, text: str) -> tuple[str, Optional[str]]:
        reply_message_id = None
        if m := re.search(r"\{REPLY:\d+}", text):
            reply_message_id = m[0][7:-1]
            text = text.replace(m[0], "")
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
            case "web_search":
                await UniMessage().text(
                    text=await lang.text("tools.search", self.session.user_id, param.get("keyword"))
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
                if ".skip" in line:
                    return
                elif ".leave" in line:
                    await self.session.mute()
                    return
            if msg:
                await self.send_text(msg)

    async def process_messages(self, msg_dict: CachedMessage) -> None:
        msg_str = generate_message_string(msg_dict)
        if len(self.openai_messages) <= 0:
            self.openai_messages.append(generate_message(msg_str, "user"))
        else:
            last_message = self.openai_messages[-1]
            if isinstance(last_message, dict) and last_message.get("role") == "user":
                if content := last_message.get("content"):
                    if isinstance(content, str):
                        last_message["content"] = content + msg_str
                else:
                    last_message["content"] = msg_str
            else:
                self.openai_messages.append(generate_message(msg_str, "user"))
        self.message_count += 1
        logger.debug(self.openai_messages)
        async with get_session() as session:
            r = await session.get(ChatGroup, {"group_id": self.session.group_id})
            self.blocked = r and msg_dict["user_id"] in json.loads(r.blocked_user)
            logger.debug(f"{self.blocked}")

    def get_message_content_list(self) -> list[str]:
        l = []
        for msg in self.openai_messages:
            if isinstance(msg, dict):
                if "content" in msg and msg["role"] == "user":
                    l.append(msg["content"])
            elif hasattr(msg, "content"):
                l.append(msg.content)
        return l

    async def generate_system_prompt(self) -> OpenAIMessage:

        # # 获取最近几条缓存消息作为上下文
        # recent_messages = self.session.cached_messages[-5:] if self.session.cached_messages else []
        # recent_context = " ".join([msg["content"] for msg in recent_messages])

        # # 激活相关记忆
        chat_history = "\n".join(self.get_message_content_list())
        # activated_memories = await activate_memories_from_text(
        #     context_id=self.session.group_id, target_message=recent_context, max_memories=5, chat_history=chat_history
        # )
        activated_memories = self.cached_activated_memories

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
        self.memory_lock = asyncio.Lock()
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
        if len(self.cached_messages) % 10 == 0 and len(self.cached_messages) > 0:
            asyncio.create_task(self.update_topic())
        if len(self.cached_messages) >= 20:
            asyncio.create_task(self.update_memory())

    async def update_topic(self) -> None:
        # # 激活相关记忆
        recent_context = self.cached_messages[-1]["content"]
        chat_history = "\n".join(self.processor.get_message_content_list())
        activated_memories = await activate_memories_from_text(
            context_id=self.group_id, target_message=recent_context, max_memories=5, chat_history=chat_history
        )
        self.processor.cached_activated_memories = activated_memories

    async def update_memory(self) -> None:
        if self.memory_lock.locked() or not self.cached_messages:
            return
        async with self.memory_lock:
            try:
                await self.generate_memory()
            except Exception as e:
                logger.exception(e)

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
        uni_msg = UniMessage()
        at_list = re.finditer("|".join([f"@{user}" for user in users.keys()]), message)
        cursor_index = 0
        for at in at_list:
            uni_msg = uni_msg.text(text=message[cursor_index : at.start()])
            at_nickname = at.group(0)[1:]
            if user_id := users.get(at_nickname):
                uni_msg = uni_msg.at(user_id)
            else:
                uni_msg = uni_msg.text(at.group(0))
            cursor_index = at.end()
        uni_msg = uni_msg.text(text=message[cursor_index:])
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
