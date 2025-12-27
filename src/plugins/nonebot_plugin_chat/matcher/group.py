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
import math
import json
import re
from nonebot_plugin_alconna import get_message_id
import random
import asyncio
from datetime import datetime, timedelta
from nonebot.adapters.qq import Bot as BotQQ
from nonebot.params import CommandArg
from nonebot.typing import T_State
from typing import Literal, TypedDict, Optional, Any
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_alconna import UniMessage, Target, get_target
from nonebot_plugin_userinfo import EventUserInfo, UserInfo

from nonebot_plugin_larkuser import get_user
from nonebot import on_message, on_command, on_notice
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters import Event, Bot, Message
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_orm import async_scoped_session, get_session
from nonebot.log import logger
from nonebot_plugin_openai import generate_message
from nonebot.adapters.onebot.v11 import GroupRecallNoticeEvent

from nonebot_plugin_openai.types import (
    Message as OpenAIMessage,
    AsyncFunction,
    FunctionParameter,
)
from nonebot_plugin_openai.utils.chat import MessageFetcher
from nonebot.matcher import Matcher

from ..lang import lang
from ..utils.note_manager import get_context_notes
from ..models import ChatGroup
from ..utils import enabled_group, parse_message_to_string
from ..utils.interrupter import Interrupter
from ..utils.tools import (
    browse_webpage,
    web_search,
    request_wolfram_alpha,
    get_note_poster,
)


def calculate_trigger_probability(accumulated_length: int) -> float:
    """
    根据累计文本长度计算触发概率

    测试：
    0 字 ->  0.00%
    10 字 ->  2.53%
    20 字 ->  3.72%
    30 字 ->  5.45%
    40 字 ->  7.90%
    50 字 -> 11.32%
    60 字 -> 15.96%
    70 字 -> 21.99%
    80 字 -> 29.45%
    90 字 -> 38.12%
    100 字 -> 47.50%
    110 字 -> 56.88%
    120 字 -> 65.55%
    130 字 -> 73.01%
    140 字 -> 79.04%
    150 字 -> 83.68%
    160 字 -> 87.10%
    180 字 -> 91.28%
    200 字 -> 93.29%

    使用 sigmoid 函数变体实现平滑过渡
    """
    if accumulated_length <= 0:
        return 0.0

    # 使用修改的 sigmoid 函数: P(x) = 0.95 / (1 + e^(-(x-100)/25))
    # 中心点在100字，斜率适中

    probability = 0.95 / (1 + math.exp(-(accumulated_length - 100) / 25))

    return max(0.0, min(0.95, probability))


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


class MessageQueue:

    def __init__(self, processor: "MessageProcessor", max_message_count: int = 10) -> None:
        self.processor = processor
        self.max_message_count = max_message_count
        self.messages: list[OpenAIMessage] = []
        self.fetcher_lock = asyncio.Lock()

    def clean_special_message(self) -> None:
        while True:
            role = get_role(self.messages[0])
            if role in ["user", "assistant"]:
                break
            self.messages.pop(0)

    async def get_messages(self) -> list[OpenAIMessage]:
        self.clean_special_message()
        self.messages = self.messages[-self.max_message_count :]
        messages = copy.deepcopy(self.messages)
        messages.insert(0, await self.processor.generate_system_prompt())
        return messages

    async def fetch_reply(self) -> None:
        if self.fetcher_lock.locked():
            return
        async with self.fetcher_lock:
            await self._fetch_reply()

    async def _fetch_reply(self) -> None:
        messages = await self.get_messages()
        self.messages.clear()
        fetcher = MessageFetcher(
            messages,
            False,
            functions=self.processor.functions,
            identify="Chat",
            pre_function_call=self.processor.send_function_call_feedback,
        )

        async for message in fetcher.fetch_message_stream():
            logger.info(f"Moonlark 说: {message}")
            fetcher.session.messages.extend(self.messages)
            self.messages = []
        self.messages = fetcher.get_messages()

    def append_user_message(self, message: str) -> None:
        self.messages.append(generate_message(message, "user"))

    def is_last_message_from_user(self) -> bool:
        return get_role(self.messages[-1]) == "user"


class MessageProcessor:

    def __init__(self, session: "GroupSession"):
        self.openai_messages = MessageQueue(self)
        self.session = session
        self.enabled = True
        self.interrupter = Interrupter(session)
        self.cold_until = datetime.now()
        self.blocked = False

        self.functions = functions = [
            AsyncFunction(
                func=self.send_message,
                description="作为 Moonlark 发送一条消息到群聊中。",
                parameters={
                    "message_content": FunctionParameter(
                        type="string",
                        description="要发送的消息内容，可以使用 @群友的昵称 来提及某位群友。",
                        required=True,
                    ),
                    "reply_message_id": FunctionParameter(
                        type="string",
                        description="要回复的消息的**消息 ID**，不指定则不会对有关消息进行引用。",
                        required=False,
                    ),
                },
            ),
            AsyncFunction(
                func=self.leave_for_a_while,
                description=("离开当前群聊 15 分钟。\n" "**何时必须调用**: Moonlark 被要求停止发言。"),
                parameters={},
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
                    "例如，当你阅读到了一个你不了解或无法确定的概念时，应优先使用此工具搜索而不是给出类似“XX是什么喵？”的回应"
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
                func=get_note_poster(self.session),
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
                        description="笔记的过期天数。如果一条笔记有一定时效性（例如它在某个日期前才有用），一定要指定本参数，默认为十年。",
                        required=False,
                    ),
                    "keywords": FunctionParameter(
                        type="string",
                        description=(
                            "笔记的关键词，每条笔记只能有 **一个** 关键词，用于索引。\n"
                            "若在笔记过期前，消息列表中出现被指定的关键词，被添加的笔记会出现在“附加信息”中。\n"
                            "关键词可以匹配消息的内容、图片的描述或发送者的昵称。\n"
                            "若不指定关键词，笔记会一直展示在“附加信息”中。"
                        ),
                        required=False,
                    ),
                },
            ),
            AsyncFunction(
                func=self.session.set_timer,
                description=(
                    "设置一个定时器，在指定时间后触发。\n"
                    "**何时必须调用**: 当需要在未来的某个时间点执行某个操作时。\n"
                    "**判断标准**: 当需要延迟执行某些操作或提醒时使用。\n"
                    "例如：群友要求你在 X 分钟后提醒他做某事；群友正在做某事，你想要几分钟后关心一下他的完成进度。\n"
                ),
                parameters={
                    "delay": FunctionParameter(
                        type="integer",
                        description="延迟时间，以分钟为单位，计时器将在此时间后触发。",
                        required=True,
                    ),
                    "description": FunctionParameter(
                        type="string",
                        description="定时器描述，用于描述定时器的用途。",
                        required=True,
                    ),
                },
            ),
        ]
        if self.session.can_send_poke():
            self.functions.append(
                AsyncFunction(
                    func=self.poke,
                    description="向指定群友发送一个戳一戳互动。",
                    parameters={
                        "target_name": FunctionParameter(
                            type="string",
                            description="被戳的群友的昵称。",
                            required=True,
                        ),
                    },
                )
            )
        asyncio.create_task(self.loop())

    async def loop(self) -> None:
        while self.enabled:
            try:
                await self.get_message()
            except Exception as e:
                logger.exception(e)
                await asyncio.sleep(10)

    async def poke(self, target_name: str) -> str:
        target_id = (await self.session.get_users()).get(target_name)
        if target_id:
            await self.session.send_poke(target_id)
            return f"你戳了戳 {target_name}。"
        else:
            return "未找到该用户"

    async def get_message(self) -> None:
        if not self.session.message_queue:
            await asyncio.sleep(3)
            return
        message, event, state, user_id, nickname, dt, mentioned, message_id = self.session.message_queue.pop(0)
        text = await parse_message_to_string(message, event, self.session.bot, state)
        if not text:
            return
        if "@Moonlark" not in text and mentioned:
            text = f"@Moonlark {text}"
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
        await self.session.on_cache_posted()
        self.interrupter.record_message()
        if (not mentioned) and await self.interrupter.should_interrupt(text, user_id):
            # 如果需要阻断，直接返回
            return
        if (mentioned or not self.session.message_queue) and not self.blocked:
            asyncio.create_task(self.generate_reply(force_reply=mentioned))

    async def handle_timer(self, description: str) -> None:
        content = f"[{datetime.now().strftime('%H:%M:%S')}]: 计时器 {description} 已触发。"
        self.openai_messages.append_user_message(content)
        await self.generate_reply(force_reply=True)

    async def handle_group_cold(self, time_d: timedelta) -> None:
        min_str = time_d.total_seconds() // 60
        if not len(self.openai_messages.messages):
            return
        delta_content = f"[{datetime.now().strftime('%H:%M:%S')}]: 当前群聊已经冷群了 {min_str} 分钟。"
        self.openai_messages.append_user_message(delta_content)
        if not self.blocked:
            asyncio.create_task(self.generate_reply())
            self.blocked = True  # 再次收到消息后才会解锁

    async def leave_for_a_while(self) -> None:
        await self.session.mute()

    async def generate_reply(self, force_reply: bool = False) -> None:
        # 如果在冷却期或消息为空，直接返回
        if self.cold_until > datetime.now():
            return
        if len(self.openai_messages.messages) <= 0 or not self.openai_messages.is_last_message_from_user():
            return
        self.cold_until = datetime.now() + timedelta(seconds=5)

        # 检查是否应该触发回复
        if not force_reply:
            probability = self.session.get_probability()
            logger.debug(
                f"Accumulated length: {self.session.accumulated_text_length}, Trigger probability: {probability:.2%}"
            )
            if random.random() > probability:
                return

        # 记录一次机器人响应
        self.interrupter.record_response()
        await self.openai_messages.fetch_reply()
        if datetime.now() < self.interrupter.sleep_end_time:
            self.interrupter.sleep_end_time = datetime.min

    async def append_tool_call_history(self, call_string: str) -> None:
        self.session.tool_calls_history.append(
            await lang.text("tools.template", self.session.user_id, datetime.now().strftime("%H:%M"), call_string)
        )
        self.session.tool_calls_history = self.session.tool_calls_history[-5:]

    async def send_function_call_feedback(
        self, call_id: str, name: str, param: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        match name:
            case "browse_webpage":
                text = await lang.text("tools.browse", self.session.user_id, param.get("url"))
            case "request_wolfram_alpha":
                text = await lang.text("tools.wolfram", self.session.user_id, param.get("question"))
            case "web_search":
                text = await lang.text("tools.search", self.session.user_id, param.get("keyword"))
            case _:
                return call_id, name, param
        await self.append_tool_call_history(text)
        return call_id, name, param

    async def send_message(self, message_content: str, reply_message_id: str | None = None) -> None:
        message = await self.session.format_message(message_content)
        if reply_message_id:
            message = message.reply(reply_message_id)
        await message.send(target=self.session.target, bot=self.session.bot)
        self.session.accumulated_text_length = 0

    def append_user_message(self, msg_str: str) -> None:
        self.openai_messages.append_user_message(msg_str)

    async def process_messages(self, msg_dict: CachedMessage) -> None:
        async with get_session() as session:
            r = await session.get(ChatGroup, {"group_id": self.session.group_id})
            self.blocked = r and msg_dict["user_id"] in json.loads(r.blocked_user)
            if not self.blocked:
                msg_str = generate_message_string(msg_dict)
                self.append_user_message(msg_str)
            if not self.blocked and not msg_dict["self"]:
                content = msg_dict.get("content", "")
                if isinstance(content, str) and content:
                    cleaned = re.sub(r"\[.*?\]", "", content)
                    cleaned = re.sub(r"\s+", " ", cleaned).strip()
                    self.session.accumulated_text_length += len(cleaned)
                logger.debug(f"Accumulated text length: {self.session.accumulated_text_length}")

    def get_message_content_list(self) -> list[str]:
        l = []
        for msg in self.openai_messages.messages:
            if isinstance(msg, dict):
                if "content" in msg and msg["role"] == "user":
                    l.append(str(msg["content"]))
            elif hasattr(msg, "content"):
                l.append(str(msg.content))
        return l

    async def generate_system_prompt(self) -> OpenAIMessage:
        chat_history = "\n".join(self.get_message_content_list())
        # 获取相关笔记
        note_manager = await get_context_notes(self.session.group_id)
        notes, notes_from_other_group = await note_manager.filter_note(chat_history)

        return generate_message(
            await lang.text(
                "prompt_group.default",
                self.session.user_id,
                "\n".join([f"- {note.content}" for note in notes]) if notes else "暂无",
                datetime.now().isoformat(),
                self.session.group_name,
                (
                    "\n".join([f"- {note.content}" for note in notes_from_other_group])
                    if notes_from_other_group
                    else "暂无"
                ),
            ),
            "system",
        )

    async def handle_recall(self, message_id: str, message_content: str) -> None:
        self.openai_messages.append_user_message(
            f"[{datetime.now().strftime('%H:%M:%S')}]: 消息 {message_id} ({message_content}) 被撤回。"
        )

    async def handle_poke(self, operator_name: str, target_name: str, to_me: bool) -> None:
        if to_me:
            self.openai_messages.append_user_message(
                f"[{datetime.now().strftime('%H:%M:%S')}]: {operator_name} 戳了戳你。"
            )
            if not self.blocked:
                await self.generate_reply(True)
                self.blocked = True
        else:
            self.openai_messages.append_user_message(
                f"[{datetime.now().strftime('%H:%M:%S')}]: {operator_name} 戳了戳 {target_name}。"
            )


from nonebot_plugin_ghot.function import get_group_hot_score


class GroupSession:

    def __init__(self, group_id: str, bot: Bot, target: Target, lang_name: str = "zh_hans") -> None:
        self.group_id = group_id
        self.adapter_group_id = target.id
        self.target = target
        self.bot = bot
        self.user_id = f"mlsid::--lang={lang_name}"
        self.tool_calls_history = []
        self.message_queue: list[tuple[UniMessage, Event, T_State, str, str, datetime, bool, str]] = []
        self.cached_messages: list[CachedMessage] = []
        self.interest_coefficient = 1
        self.message_cache_counter = 0
        self.ghot_coefficient = 1
        self.accumulated_text_length = 0  # 累计文本长度
        self.last_reward_participation: Optional[datetime] = None
        self.mute_until: Optional[datetime] = None
        self.group_users: dict[str, str] = {}
        self.setup_time = datetime.now()
        self.user_counter: dict[datetime, set[str]] = {}
        self.group_name = "未命名群聊"
        self.llm_timers = []  # 定时器列表
        self.processor = MessageProcessor(self)
        asyncio.create_task(self.setup_group_name())
        asyncio.create_task(self.calculate_ghot_coefficient())

    async def send_poke(self, target_id: str) -> None:
        await self.bot.call_api("group_poke", group_id=int(self.adapter_group_id), user_id=int(target_id))

    def can_send_poke(self) -> bool:
        return self.bot.self_id in config.napcat_bot_ids

    async def set_interest_coefficient(self, mode: Literal["low", "medium", "high"]) -> None:
        self.interest_coefficient = {
            "low": 0.5,
            "medium": 1,
            "high": 1.2,
        }[mode]

    def get_probability(self, length_adjustment: int = 0, apply_ghot_coeefficient: bool = True) -> float:
        """
        计算触发回复的概率

        参数:
            length_adjustment: 对累计文本长度的调整值，默认为0

        返回:
            触发回复的概率值（0.0-1.0之间）
        """
        # 使用调整后的累计文本长度
        adjusted_length = self.accumulated_text_length + length_adjustment

        # 使用 calculate_trigger_probability 函数计算基础概率
        base_probability = calculate_trigger_probability(adjusted_length)

        # 应用热度系数
        if apply_ghot_coeefficient:
            final_probability = base_probability * self.ghot_coefficient
        else:
            final_probability = base_probability

        # 确保概率在 0.0-1.0 之间
        return max(0.0, min(1.0, final_probability))

    async def calculate_ghot_coefficient(self) -> None:
        self.ghot_coefficient = round(max((12 - (await get_group_hot_score(self.group_id))[2]) * 0.8, 1))
        cached_users = set()
        for message in self.cached_messages[:-5]:
            if not message["self"]:
                cached_users.add(message["user_id"])
        if len(cached_users) <= 1:
            self.ghot_coefficient *= 0.75

    def clean_cached_message(self) -> None:
        if len(self.cached_messages) > 50:
            self.cached_messages = self.cached_messages[-50:]

    async def on_cache_posted(self) -> None:
        self.message_cache_counter += 1
        self.clean_cached_message()
        if self.message_cache_counter % 50 == 0:
            await self.setup_group_name()
        elif self.message_cache_counter % 10 == 0:
            await self.calculate_ghot_coefficient()

    async def mute(self) -> None:
        self.mute_until = datetime.now() + timedelta(minutes=15)

    async def setup_group_name(self) -> None:
        if isinstance(self.bot, OB11Bot):
            self.group_name = (await self.bot.get_group_info(group_id=int(self.adapter_group_id)))["group_name"]

    async def handle_message(
        self, message: UniMessage, user_id: str, event: Event, state: T_State, nickname: str, mentioned: bool = False
    ) -> None:
        message_id = get_message_id(event)
        self.message_queue.append((message, event, state, user_id, nickname, datetime.now(), mentioned, message_id))

    async def format_message(self, origin_message: str) -> UniMessage:
        message = re.sub(r"\[\d\d:\d\d:\d\d]\[Moonlark]\(\d+\): ?", "", origin_message)
        message = message.strip()
        users = await self.get_users()
        uni_msg = UniMessage()
        at_list = re.finditer("|".join([f"@{re.escape(user)}" for user in users.keys()]), message)
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

    async def _get_users_in_cached_message(self) -> dict[str, str]:
        users = {}
        for message in self.cached_messages:
            if not message["self"]:
                users[message["nickname"]] = message["user_id"]
        return users

    async def get_users(self) -> dict[str, str]:
        cached_users = await self._get_users_in_cached_message()
        if any([u not in self.group_users for u in cached_users.keys()]):
            if isinstance(self.bot, OB11Bot):
                self.group_users.clear()
                for user in await self.bot.get_group_member_list(group_id=int(self.adapter_group_id)):
                    self.group_users[user["nickname"]] = str(user["user_id"])
            else:
                self.group_users = cached_users
        return self.group_users

    async def process_timer(self) -> None:
        dt = datetime.now()
        if self.mute_until and dt > self.mute_until:
            self.mute_until = None

        triggered_timers = []
        for timer in self.llm_timers:
            if dt >= timer["trigger_time"]:
                description = timer["description"]
                await self.processor.handle_timer(description)
                triggered_timers.append(timer)
        for timer in triggered_timers:
            self.llm_timers.remove(timer)

        if self.processor.blocked or not self.cached_messages:
            return
        if (dt - self.setup_time).total_seconds() // 60 % 10 == 0:
            await self.calculate_ghot_coefficient()
        time_to_last_message = (dt - self.cached_messages[-1]["send_time"]).total_seconds()
        # 如果群聊冷却超过3分钟，根据累计文本长度判断是否主动发言
        if 90 < time_to_last_message < 300 and not self.cached_messages[-1]["self"]:
            probability = self.get_probability()
            if random.random() <= probability:
                await self.processor.handle_group_cold(timedelta(seconds=time_to_last_message))

    async def get_cached_messages_string(self) -> str:
        messages = []
        for message in self.cached_messages:
            messages.append(
                f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]: {message['content']}"
            )
        return "\n".join(messages)

    async def handle_poke(self, event: PokeNotifyEvent, nickname: str) -> None:
        user = await get_user(str(event.target_id))
        if event.group_id and (isinstance(self.bot, OB11Bot) or not user.has_nickname()):
            info = await self.bot.get_group_member_info(group_id=event.group_id, user_id=event.target_id)
            target_nickname = info["nickname"]
        else:
            target_nickname = user.get_nickname()
        await self.processor.handle_poke(nickname, target_nickname, event.is_tome())

    async def handle_recall(self, message_id: str) -> None:
        for message in self.cached_messages:
            if message["message_id"] == message_id:
                message_content = message["content"]
                break
        else:
            message_content = "消息内容获取失败"

        await self.processor.handle_recall(message_id, message_content)

    async def set_timer(self, delay: int, description: str = ""):
        """
        设置定时器

        Args:
            delay: 延迟时间（分钟）
            description: 定时器描述
        """
        # 获取当前时间
        now = datetime.now()
        # 计算触发时间（将分钟转换为秒）
        trigger_time = now + timedelta(minutes=delay)

        # 生成定时器ID
        timer_id = f"{self.group_id}_{now.timestamp()}"

        # 存储定时器信息
        self.llm_timers.append({"id": timer_id, "trigger_time": trigger_time, "description": description})

        return f"定时器已设置，将在 {delay} 分钟后触发"


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


class CommandHandler:

    def __init__(
        self, mathcer: Matcher, bot: Bot, session: async_scoped_session, message: Message, group_id: str, user_id: str
    ):
        self.matcher = mathcer
        self.bot = bot
        self.session = session
        self.group_id = group_id
        self.user_id = user_id
        self.argv = message.extract_plain_text().split(" ")
        self.group_config = ChatGroup(group_id=self.group_id, enabled=False)

    async def setup(self) -> "CommandHandler":
        if isinstance(self.bot, BotQQ):
            await lang.finish("command.not_available", self.user_id)
        self.group_config = (await self.session.get(ChatGroup, {"group_id": self.group_id})) or ChatGroup(
            group_id=self.group_id, enabled=False
        )
        return self

    def is_group_enabled(self) -> bool:
        return self.group_config.enabled

    async def handle_switch(self) -> None:
        if self.is_group_enabled():
            await self.handle_off()
        else:
            await self.handle_on()

    async def merge_group_config(self) -> None:
        await self.session.merge(self.group_config)
        await self.session.commit()

    async def handle_off(self) -> None:
        self.group_config.enabled = False
        await self.merge_group_config()
        await group_disable(self.group_id)
        await lang.finish("command.switch.disabled", self.user_id)

    async def handle_on(self) -> None:
        self.group_config.enabled = True
        await self.merge_group_config()
        await lang.finish("command.switch.enabled", self.user_id)

    async def handle_desire(self) -> None:
        session = await self.get_group_session()
        length = session.accumulated_text_length
        probability = session.get_probability(apply_ghot_coeefficient=False)
        await lang.send("command.desire.get", self.user_id, length, round(probability, 2), session.ghot_coefficient)

    async def handle_mute(self) -> None:
        session = await self.get_group_session()
        await session.mute()
        await lang.finish("command.mute", self.user_id)

    async def handle_unmute(self) -> None:
        session = await self.get_group_session()
        session.mute_until = None
        await lang.finish("command.unmute", self.user_id)

    async def handle_calls(self) -> None:
        session = await self.get_group_session()
        await self.matcher.finish("\n".join(session.tool_calls_history))

    async def handle(self) -> None:
        match self.argv[0]:
            case "switch":
                await self.handle_switch()
            case "desire":
                await self.handle_desire()
            case "mute":
                await self.handle_mute()
            case "unmute":
                await self.handle_unmute()
            case "calls":
                await self.handle_calls()
            case "on":
                await self.handle_on()
            case "off":
                await self.handle_off()
            case _:
                await lang.finish("command.no_argv", self.user_id)

    async def get_group_session(self) -> GroupSession:
        if self.group_id in groups:
            return groups[self.group_id]
        elif self.is_group_enabled():
            await lang.finish("command.not_inited", self.user_id)
        else:
            await lang.finish("command.disabled", self.user_id)


@on_command("chat").handle()
async def _(
    matcher: Matcher,
    bot: Bot,
    session: async_scoped_session,
    message: Message = CommandArg(),
    group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    handler = CommandHandler(matcher, bot, session, message, group_id, user_id)
    await handler.setup()
    await handler.handle()


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


@on_notice().handle()
async def _(event: GroupRecallNoticeEvent, group_id: str = get_group_id()) -> None:
    message_id = str(event.message_id)
    if group_id not in groups:
        return
    session = groups[group_id]
    await session.handle_recall(message_id)


@on_notice().handle()
async def _(
    event: PokeNotifyEvent,
    moonlark_group_id: str = get_group_id(),
    user_info: UserInfo = EventUserInfo(),
    user_id: str = get_user_id(),
) -> None:
    if moonlark_group_id not in groups:
        return
    session = groups[moonlark_group_id]
    user = await get_user(user_id)
    if user.has_nickname():
        nickname = user.get_nickname()
    else:
        nickname = user_info.user_displayname or user_info.user_name
    await session.handle_poke(event, nickname)
