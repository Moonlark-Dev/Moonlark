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

from abc import ABC, abstractmethod
import copy
import math
import json
import re
from nonebot.adapters.onebot.v11 import NoticeEvent
from nonebot_plugin_alconna import get_message_id
import random
import asyncio
from datetime import datetime, timedelta
from nonebot.adapters.qq import Bot as BotQQ
from nonebot.params import CommandArg
from nonebot.typing import T_State
from typing import AsyncGenerator, Literal, TypedDict, Optional, Any, cast
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_alconna import UniMessage, Target, get_target
from nonebot.adapters.onebot.v11.event import FriendRecallNoticeEvent
from nonebot_plugin_chat.utils.ai_agent import AskAISession
from nonebot_plugin_chat.utils.message import parse_dict_message
from nonebot_plugin_chat.utils.sticker_manager import get_sticker_manager
from nonebot_plugin_larkuser import get_nickname

from nonebot_plugin_larkuser import get_user
from nonebot import get_driver, on_message, on_command, on_notice
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters import Event, Bot, Message
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot_plugin_larkutils import get_user_id, get_group_id
from nonebot_plugin_larkutils.subaccount import get_main_account
from nonebot_plugin_larkutils.user import private_message
from nonebot_plugin_orm import async_scoped_session, get_session
from nonebot.log import logger
from nonebot_plugin_openai import generate_message
from nonebot.adapters.onebot.v11 import GroupRecallNoticeEvent

from nonebot_plugin_openai.types import (
    FunctionParameterWithEnum,
    Message as OpenAIMessage,
    AsyncFunction,
    FunctionParameter,
)
from nonebot_plugin_openai.utils.chat import MessageFetcher
from nonebot.matcher import Matcher
from sqlalchemy import select

from ..lang import lang
from ..utils.note_manager import get_context_notes
from ..models import ChatGroup, RuaAction, Sticker, UserProfile, MessageQueueCache
from ..utils import enabled_group, parse_message_to_string
from ..utils.image import query_image_content
from ..utils.tools import (
    browse_webpage,
    web_search,
    request_wolfram_alpha,
    search_abbreviation,
    get_note_poster,
    get_note_remover,
)
import uuid
from ..utils.tools.sticker import StickerTools


class PendingInteraction(TypedDict):
    """待处理的交互请求"""

    interaction_id: str
    user_id: str
    nickname: str
    action: RuaAction
    created_at: float  # timestamp


QQ_EMOJI_MAP = {
    "4": "得意",
    "5": "流泪",
    "8": "睡",
    "9": "大哭",
    "10": "尴尬",
    "12": "调皮",
    "14": "微笑",
    "16": "酷",
    "21": "可爱",
    "23": "傲慢",
    "24": "饥饿",
    "25": "困",
    "26": "惊恐",
    "27": "流汗",
    "28": "憨笑",
    "29": "悠闲",
    "30": "奋斗",
    "32": "疑问",
    "33": "嘘",
    "34": "晕",
    "38": "敲打",
    "39": "再见",
    "41": "发抖",
    "42": "爱情",
    "43": "跳跳",
    "49": "拥抱",
    "53": "蛋糕",
    "60": "咖啡",
    "63": "玫瑰",
    "66": "爱心",
    "74": "太阳",
    "75": "月亮",
    "76": "赞",
    "78": "握手",
    "79": "胜利",
    "85": "飞吻",
    "89": "西瓜",
    "96": "冷汗",
    "97": "擦汗",
    "98": "抠鼻",
    "99": "鼓掌",
    "100": "糗大了",
    "101": "坏笑",
    "102": "左哼哼",
    "103": "右哼哼",
    "104": "哈欠",
    "106": "委屈",
    "109": "左亲亲",
    "111": "可怜",
    "116": "示爱",
    "118": "抱拳",
    "120": "拳头",
    "122": "爱你",
    "123": "NO",
    "124": "OK",
    "125": "转圈",
    "129": "挥手",
    "144": "喝彩",
    "147": "棒棒糖",
    "171": "茶",
    "173": "泪奔",
    "174": "无奈",
    "175": "卖萌",
    "176": "小纠结",
    "179": "doge",
    "180": "惊喜",
    "181": "骚扰",
    "182": "笑哭",
    "183": "我最美",
    "201": "点赞",
    "203": "托脸",
    "212": "托腮",
    "214": "啵啵",
    "219": "蹭一蹭",
    "222": "抱抱",
    "227": "拍手",
    "232": "佛系",
    "240": "喷脸",
    "243": "甩头",
    "246": "加油抱抱",
    "262": "脑阔疼",
    "264": "捂脸",
    "265": "辣眼睛",
    "266": "哦哟",
    "267": "头秃",
    "268": "问号脸",
    "269": "暗中观察",
    "270": "emm",
    "271": "吃瓜",
    "272": "呵呵哒",
    "273": "我酸了",
    "277": "汪汪",
    "278": "汗",
    "281": "无眼笑",
    "282": "敬礼",
    "284": "面无表情",
    "285": "摸鱼",
    "287": "哦",
    "289": "睁眼",
    "290": "敲开心",
    "293": "摸锦鲤",
    "294": "期待",
    "297": "拜谢",
    "298": "元宝",
    "299": "牛啊",
    "305": "右亲亲",
    "306": "牛气冲天",
    "307": "喵喵",
    "314": "仔细分析",
    "315": "加油",
    "318": "崇拜",
    "319": "比心",
    "320": "庆祝",
    "322": "拒绝",
    "324": "吃糖",
    "326": "生气",
    "9728": "☀",
    "9749": "☕",
    "9786": "☺",
    "10024": "✨",
    "10060": "❌",
    "10068": "❔",
    "127801": "🌹",
    "127817": "🍉",
    "127822": "🍎",
    "127827": "🍓",
    "127836": "🍜",
    "127838": "🍞",
    "127847": "🍧",
    "127866": "🍺",
    "127867": "🍻",
    "127881": "🎉",
    "128027": "🐛",
    "128046": "🐮",
    "128051": "🐳",
    "128053": "🐵",
    "128074": "👊",
    "128076": "👌",
    "128077": "👍",
    "128079": "👏",
    "128089": " bikini",
    "128102": "👦",
    "128104": "👨",
    "128147": "💓",
    "128157": "💝",
    "128164": "💤",
    "128166": "💦",
    "128168": "💨",
    "128170": "💪",
    "128235": "📫",
    "128293": "🔥",
    "128513": "😁",
    "128514": "😂",
    "128516": "😄",
    "128522": "😊",
    "128524": "😌",
    "128527": "😏",
    "128530": "😒",
    "128531": "😓",
    "128532": "😔",
    "128536": "😘",
    "128538": "😚",
    "128540": "😜",
    "128541": "😝",
    "128557": "😭",
    "128560": "😰",
    "128563": "😳",
}


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

    def __init__(
        self,
        processor: "MessageProcessor",
        max_message_count: int = 50,
        consecutive_warning_threshold: int = 5,
        consecutive_stop_threshold: int = 10,
    ) -> None:
        self.processor = processor
        self.max_message_count = max_message_count
        self.messages: list[OpenAIMessage] = []
        self.CONSECUTIVE_WARNING_THRESHOLD = consecutive_warning_threshold
        self.CONSECUTIVE_STOP_THRESHOLD = consecutive_stop_threshold
        self.fetcher_lock = asyncio.Lock()
        self.cached_reasoning_content = ""
        self.consecutive_bot_messages = 0  # 连续发送消息计数器
        # 恢复完成事件，用于确保在处理消息前恢复已完成
        self._restore_complete = asyncio.Event()
        # 在初始化时从数据库恢复消息队列
        self.inserted_messages = []
        asyncio.create_task(self._restore_from_db())

    async def wait_for_restore(self) -> None:
        """等待数据库恢复完成"""
        await self._restore_complete.wait()

    def _serialize_message(self, message: OpenAIMessage) -> dict:
        """将 OpenAIMessage 序列化为可 JSON 化的字典"""
        if isinstance(message, dict):
            return message  # type: ignore
        # 如果是 Pydantic 模型或其他对象，转换为字典
        if hasattr(message, "model_dump"):
            return message.model_dump()
        elif hasattr(message, "__dict__"):
            return dict(message.__dict__)
        else:
            return {"content": str(message), "role": "user"}

    def _serialize_messages(self) -> str:
        """将消息列表序列化为 JSON 字符串"""
        serialized = [self._serialize_message(msg) for msg in self.messages]
        return json.dumps(serialized, ensure_ascii=False)

    async def _restore_from_db(self) -> None:
        """从数据库恢复消息队列"""
        try:
            group_id = self.processor.session.session_id
            async with get_session() as session:
                cache = await session.get(MessageQueueCache, {"group_id": group_id})
                if cache:
                    self.messages = json.loads(cache.messages_json)
                    self.consecutive_bot_messages = cache.consecutive_bot_messages
                    logger.info(f"已从数据库恢复群 {group_id} 的消息队列，共 {len(self.messages)} 条消息")
        except Exception as e:
            logger.warning(f"从数据库恢复消息队列失败: {e}")
        finally:
            # 无论恢复成功与否，都设置恢复完成事件
            self._restore_complete.set()

    async def save_to_db(self) -> None:
        """将消息队列保存到数据库"""
        try:
            async with self.fetcher_lock:
                group_id = self.processor.session.session_id
                async with get_session() as session:
                    cache = MessageQueueCache(
                        group_id=group_id,
                        messages_json=self._serialize_messages(),
                        consecutive_bot_messages=self.consecutive_bot_messages,
                        updated_time=datetime.now().timestamp(),
                    )
                    await session.merge(cache)
                    await session.commit()
        except Exception as e:
            logger.exception(e)

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
            retried = False
            while not await self._fetch_reply() and not retried:
                retried = True
                self.append_user_message(
                    await self.processor.session.text(
                        "prompt.warning.invalid_tool_call",
                        datetime.now().strftime("%H:%M:%S"),
                    ),
                    False,
                )

    async def _fetch_reply(self) -> bool:
        messages = await self.get_messages()
        self.messages.clear()
        self.inserted_messages.clear()
        fetcher = await MessageFetcher.create(
            messages,
            False,
            functions=self.processor.functions,
            identify="Chat",
            pre_function_call=self.processor.send_function_call_feedback,
        )
        include_wrong_tool_calls = False
        try:
            async for message in fetcher.fetch_message_stream():
                if message.startswith("## 思考过程"):
                    self.cached_reasoning_content = message
                logger.info(f"Moonlark 说: {message}")
                fetcher.session.insert_messages(self.messages)
                self.inserted_messages.extend(self.messages)
                self.messages = []
                if any([keyword in message for keyword in ["<parameter", "</function_calls>", "<function"]]):
                    include_wrong_tool_calls = True
            self.messages = fetcher.get_messages()
        except Exception as e:
            logger.exception(e)
            # 恢复 Message
            self.messages = messages + self.inserted_messages
            self.inserted_messages.clear()
        return not include_wrong_tool_calls

    def append_user_message(self, message: str, reset_bot_message_counter: bool = True) -> None:
        if reset_bot_message_counter:
            self.consecutive_bot_messages = 0  # 收到用户消息时重置计数器
        self.messages.append(generate_message(message, "user"))

    def is_last_message_from_user(self) -> bool:
        return get_role(self.messages[-1]) == "user"

    def increment_bot_message_count(self) -> None:
        """增加 bot 发送消息计数"""
        self.consecutive_bot_messages += 1

    def should_warn_excessive_messages(self) -> bool:
        """检查是否应该发出过多消息警告"""
        return self.consecutive_bot_messages == self.CONSECUTIVE_WARNING_THRESHOLD

    def should_stop_response(self) -> bool:
        """检查是否应该停止响应（超过限制）"""
        return self.consecutive_bot_messages >= self.CONSECUTIVE_STOP_THRESHOLD

    async def insert_warning_message(self) -> None:
        """向消息队列中插入警告消息"""
        warning = await self.processor.session.text("prompt.warning.excessive_messages", self.consecutive_bot_messages)
        self.messages.append(generate_message(warning, "user"))


class AdapterUserInfo(TypedDict):
    sex: Literal["male", "female", "unknown"]
    role: Literal["member", "admin", "owner", "user"]
    nickname: str
    join_time: int
    card: Optional[str]


class MessageProcessor:

    def __init__(self, session: "BaseSession"):
        self.openai_messages = MessageQueue(self, 50)
        self.session = session
        self.enabled = True
        self.ai_agent = AskAISession(self.session.lang_str)
        self.sticker_manager = get_sticker_manager()
        self.cold_until = datetime.now()
        self.blocked = False
        self._latest_reasioning_content_cache = ""
        self.sticker_tools = StickerTools(self.session)
        self.functions = []

    async def query_image(self, image_id: str, query_prompt: str) -> str:
        return await query_image_content(image_id, query_prompt, self.session.lang_str)

    async def setup(self) -> None:

        self.functions = [
            AsyncFunction(
                func=self.query_image,
                description=await self.session.text("tools_desc.query_image.desc"),
                parameters={
                    "image_id": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.query_image.image_id"),
                        required=True,
                    ),
                    "query_prompt": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.query_image.query_prompt"),
                        required=True,
                    ),
                },
            ),
            AsyncFunction(
                func=self.send_message,
                description=await self.session.text("tools_desc.send_message.desc"),
                parameters={
                    "message_content": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.send_message.message_content"),
                        required=True,
                    ),
                    "reply_message_id": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.send_message.reply_message_id"),
                        required=False,
                    ),
                },
            ),
            AsyncFunction(
                func=self.leave_for_a_while,
                description=await self.session.text("tools_desc.leave_for_a_while.desc"),
                parameters={},
            ),
            AsyncFunction(
                func=browse_webpage,
                description=await self.session.text("tools_desc.browse_webpage.desc"),
                parameters={
                    "url": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.browse_webpage.url"),
                        required=True,
                    )
                },
            ),
            AsyncFunction(
                func=web_search,
                description=await self.session.text("tools_desc.web_search.desc"),
                parameters={
                    "keyword": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.web_search.keyword"),
                        required=True,
                    )
                },
            ),
            AsyncFunction(
                func=request_wolfram_alpha,
                description=await self.session.text("tools_desc.request_wolfram_alpha.desc"),
                parameters={
                    "question": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.request_wolfram_alpha.question"),
                        required=True,
                    )
                },
            ),
            AsyncFunction(
                func=search_abbreviation,
                description=await self.session.text("tools_desc.search_abbreviation.desc"),
                parameters={
                    "text": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.search_abbreviation.text"),
                        required=True,
                    )
                },
            ),
            AsyncFunction(
                func=get_note_poster(self.session),
                description=await self.session.text("tools_desc.get_note_poster.desc"),
                parameters={
                    "text": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.get_note_poster.text"),
                        required=True,
                    ),
                    "expire_days": FunctionParameter(
                        type="integer",
                        description=await self.session.text("tools_desc.get_note_poster.expire_days"),
                        required=False,
                    ),
                    "keywords": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.get_note_poster.keywords"),
                        required=False,
                    ),
                },
            ),
            AsyncFunction(
                func=get_note_remover(self.session),
                description=await self.session.text("tools_desc.get_note_remover.desc"),
                parameters={
                    "note_id": FunctionParameter(
                        type="integer",
                        description=await self.session.text("tools_desc.get_note_remover.note_id"),
                        required=True,
                    ),
                },
            ),
            AsyncFunction(
                func=self.session.set_timer,
                description=await self.session.text("tools_desc.set_timer.desc"),
                parameters={
                    "delay": FunctionParameter(
                        type="integer",
                        description=await self.session.text("tools_desc.set_timer.delay"),
                        required=True,
                    ),
                    "description": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.set_timer.description"),
                        required=True,
                    ),
                },
            ),
            AsyncFunction(
                func=self.sticker_tools.save_sticker,
                description=await self.session.text("tools_desc.save_sticker.desc"),
                parameters={
                    "image_id": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.save_sticker.image_id"),
                        required=True,
                    ),
                },
            ),
            AsyncFunction(
                func=self.sticker_tools.search_sticker,
                description=await self.session.text("tools_desc.search_sticker.desc"),
                parameters={
                    "query": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.search_sticker.query"),
                        required=True,
                    ),
                },
            ),
            AsyncFunction(
                func=self.sticker_tools.send_sticker,
                description=await self.session.text("tools_desc.send_sticker.desc"),
                parameters={
                    "sticker_id": FunctionParameter(
                        type="integer",
                        description=await self.session.text("tools_desc.send_sticker.sticker_id"),
                        required=True,
                    ),
                },
            ),
            AsyncFunction(
                func=self.ai_agent.ask_ai,
                description=await self.session.text("tools_desc.ask_ai.desc"),
                parameters={
                    "query": FunctionParameter(
                        type="string",
                        required=True,
                        description=await self.session.text("tools_desc.ask_ai.query"),
                    ),
                },
            ),
            AsyncFunction(
                func=self.refuse_interaction_request,
                description=await self.session.text("tools_desc.refuse_interaction_request.desc"),
                parameters={
                    "id_": FunctionParameter(
                        type="string",
                        description=await self.session.text("tools_desc.refuse_interaction_request.id_"),
                        required=True,
                    ),
                    "type_": FunctionParameterWithEnum(
                        type="string",
                        description=await self.session.text("tools_desc.refuse_interaction_request.type_"),
                        required=True,
                        enum={"dodge", "bite"},
                    ),
                },
            ),
        ]

        if self.session.is_napcat_bot():
            self.functions.extend(
                [
                    AsyncFunction(
                        func=self.poke,
                        description=await self.session.text("tools_desc.poke.desc"),
                        parameters={
                            "target_name": FunctionParameter(
                                type="string",
                                description=await self.session.text("tools_desc.poke.target_name"),
                                required=True,
                            ),
                        },
                    ),
                ]
            )
        if isinstance(self.session.bot, OB11Bot):
            self.functions.append(
                AsyncFunction(
                    func=self.delete_message,
                    description=await self.session.text("tools_desc.delete_message.desc"),
                    parameters={
                        "message_id": FunctionParameter(
                            type="integer",
                            description=await self.session.text("tools_desc.delete_message.message_id"),
                            required=True,
                        )
                    },
                )
            )
        if isinstance(self.session, GroupSession):
            emoji_id_table = ", ".join([f"{emoji}({emoji_id})" for emoji_id, emoji in QQ_EMOJI_MAP.items()])
            self.functions.append(
                AsyncFunction(
                    func=self.send_reaction,
                    description=await self.session.text("tools_desc.send_reaction.desc", emoji_id_table),
                    parameters={
                        "message_id": FunctionParameter(
                            type="string",
                            description=await self.session.text("tools_desc.send_reaction.message_id"),
                            required=True,
                        ),
                        "emoji_id": FunctionParameterWithEnum(
                            type="string",
                            description=await self.session.text("tools_desc.send_reaction.emoji_id"),
                            required=True,
                            enum=set(QQ_EMOJI_MAP.keys()),
                        ),
                    },
                )
            )
        asyncio.create_task(self.loop())

    async def delete_message(self, message_id: int) -> str:
        if isinstance(self.session.bot, OB11Bot):
            await self.session.bot.delete_msg(message_id=message_id)
            return await self.session.text("message.deleted")
        return await self.session.text("message.delete_failed")

    async def send_reaction(self, message_id: str, emoji_id: str) -> str:
        if isinstance(self.session.bot, OB11Bot) and self.session.is_napcat_bot():
            await self.session.bot.call_api("set_msg_emoji_like", message_id=message_id, emoji_id=emoji_id)
            return await self.session.text("message.reaction_success", QQ_EMOJI_MAP.get(emoji_id))
        else:
            return await self.session.text("message.reaction_failed")

    async def refuse_interaction_request(self, id_: str, type_: Literal["dodge", "bite"]) -> str:
        """
        拒绝交互请求

        Args:
            id_: 交互请求 ID
            type_: 拒绝类型，dodge（躲开）或 bite（躲开并咬一口）

        Returns:
            处理结果消息
        """
        interaction = self.session.remove_pending_interaction(id_)
        if interaction is None:
            return await self.session.text("interaction.not_found")

        action_name = interaction["action"]["name"]
        nickname = interaction["nickname"]

        # 根据拒绝类型生成不同的提示
        if type_ == "dodge":
            # 发送拒绝消息到会话
            refuse_msg = await self.session.text(f"rua.actions.{action_name}.refuse_msg")
            await self.send_message(refuse_msg)
            return await self.session.text(f"rua.actions.{action_name}.refuse_prompt", nickname)
        else:  # bite
            # 躲开并咬一口
            refuse_msg = await self.session.text("rua.bite_msg", nickname)
            await self.send_message(refuse_msg)
            return await self.session.text("rua.bite_prompt", nickname)

    async def loop(self) -> None:
        # 在开始循环前等待消息队列从数据库恢复完成
        await self.openai_messages.wait_for_restore()
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
            return await self.session.text("poke.success", target_name)
        else:
            return await self.session.text("poke.not_found")

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
        if (mentioned or not self.session.message_queue) and not self.blocked:
            asyncio.create_task(self.generate_reply(force_reply=mentioned))

    async def handle_timer(self, description: str) -> None:
        content = await self.session.text("prompt.timer_triggered", datetime.now().strftime("%H:%M:%S"), description)
        self.openai_messages.append_user_message(content)
        await self.generate_reply(force_reply=True)

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
            probability = await self.session.get_probability()
            logger.debug(
                f"Accumulated length: {self.session.accumulated_text_length}, Trigger probability: {probability:.2%}"
            )
            if random.random() > probability:
                return

        logger.info(f"Generating reply ({force_reply=})...")
        await self.openai_messages.fetch_reply()

    async def append_tool_call_history(self, call_string: str) -> None:
        self.session.tool_calls_history.append(
            await self.session.text("tools.template", datetime.now().strftime("%H:%M"), call_string)
        )
        self.session.tool_calls_history = self.session.tool_calls_history[-5:]

    async def send_function_call_feedback(
        self, call_id: str, name: str, param: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        match name:
            case "browse_webpage":
                text = await self.session.text("tools.browse", param.get("url"))
            case "request_wolfram_alpha":
                text = await self.session.text("tools.wolfram", param.get("question"))
            case "web_search":
                text = await self.session.text("tools.search", param.get("keyword"))
            case _:
                return call_id, name, param
        await self.append_tool_call_history(text)
        return call_id, name, param

    async def send_message(self, message_content: str, reply_message_id: str | None = None) -> str:
        # 增加连续发送消息计数
        self.openai_messages.increment_bot_message_count()
        self.session.last_activate = datetime.now()

        # 检查是否超过停止阈值
        if self.openai_messages.should_stop_response():
            logger.warning(f"Bot 连续发送消息超过 {self.openai_messages.CONSECUTIVE_STOP_THRESHOLD} 条，强制停止响应")
            return await self.session.text("message.stop_response", self.openai_messages.consecutive_bot_messages)

        # 检查是否需要发出警告
        if self.openai_messages.should_warn_excessive_messages():
            logger.warning(f"Bot 连续发送消息达到 {self.openai_messages.CONSECUTIVE_WARNING_THRESHOLD} 条，插入警告")
            await self.openai_messages.insert_warning_message()

        message = await self.session.format_message(message_content)
        if reply_message_id:
            message = message.reply(reply_message_id)
        receipt = await message.send(target=self.session.target, bot=self.session.bot)
        self.session.accumulated_text_length = 0
        message_id = receipt.msg_ids[0] if receipt.msg_ids else None
        message_id = message_id["message_id"] if message_id else await self.session.text("prompt.recall_failed")
        response = await self.session.text("message.sent", message_id)
        if self.openai_messages.cached_reasoning_content != self._latest_reasioning_content_cache:
            sticker_recommendations = "\n".join(
                await self.get_sticker_recommendations(self.openai_messages.cached_reasoning_content)
            )
            if sticker_recommendations:
                response += await self.session.text("sticker.recommend", sticker_recommendations)
        return response

    def append_user_message(self, msg_str: str) -> None:
        self.openai_messages.append_user_message(msg_str)

    async def process_messages(self, msg_dict: CachedMessage) -> None:
        async with get_session() as session:
            r = await session.get(ChatGroup, {"group_id": self.session.session_id})

            # Check for blocked user
            blocked_user = r and msg_dict["user_id"] in json.loads(r.blocked_user)

            # Check for blocked keywords
            blocked_keyword = False
            if r:
                keywords = json.loads(r.blocked_keyword)
                content = msg_dict.get("content", "")
                if isinstance(content, str):
                    for keyword in keywords:
                        if keyword in content:
                            blocked_keyword = True
                            break

            self.blocked = blocked_user or blocked_keyword

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

    async def _get_user_profiles(self) -> list[str]:
        """根据昵称获取用户的 profile 信息"""
        profiles = []
        async with get_session() as session:
            for nickname, user_id in (await self.session._get_users_in_cached_message()).items():
                if not (profile := await session.get(UserProfile, {"user_id": user_id})):
                    profile = await self.session.text("prompt_group.user_profile_not_found")
                    is_profile_found = False
                else:
                    profile = profile.profile_content
                    is_profile_found = True
                if isinstance(self.session.bot, OB11Bot):
                    try:
                        member_info = await self.session.get_user_info(user_id)
                    except Exception as e:
                        member_info = None
                else:
                    member_info = None
                user = await get_user(user_id)
                fav = user.get_fav()
                fav_level = await user.get_fav_level()
                if member_info:
                    profiles.append(
                        await self.session.text(
                            "prompt_group.group_member_info",
                            nickname,
                            member_info["role"],
                            member_info["sex"],
                            fav,
                            fav_level,
                            datetime.fromtimestamp(member_info["join_time"]).strftime("%Y-%m-%d"),
                            profile,
                        )
                    )
                elif fav > 0 or is_profile_found:
                    profiles.append(
                        await self.session.text("prompt_group.member_info", nickname, fav, fav_level, profile)
                    )
        return profiles

    async def generate_sticker_recommendations(self, reasoning_text: str) -> AsyncGenerator[str, None]:
        """
        根据聊天记录的上下文关键词获取表情包推荐

        Returns:
            推荐的表情包列表（格式为 "ID: 描述"）
        """
        chat_history = "\n".join(self.get_message_content_list())
        async with get_session() as session:
            results = await session.scalars(
                select(Sticker).where(
                    Sticker.context_keywords.isnot(None), Sticker.emotion.isnot(None), Sticker.labels.isnot(None)
                )
            )
            for sticker in results:
                if sticker.emotion and sticker.emotion in reasoning_text:
                    yield f"- {sticker.id}: {sticker.description}"
                    break
                for keyword in json.loads(sticker.context_keywords or "[]"):
                    if keyword in chat_history:
                        yield f"- {sticker.id}: {sticker.description}"
                        break
                for label in json.loads(sticker.labels or "[]"):
                    if label in chat_history or label in reasoning_text:
                        yield f"- {sticker.id}: {sticker.description}"
                        break

    async def get_sticker_recommendations(self, reasoning_text: str) -> list[str]:
        return [sticker async for sticker in self.generate_sticker_recommendations(reasoning_text)]

    async def generate_system_prompt(self) -> OpenAIMessage:
        chat_history = "\n".join(self.get_message_content_list())
        # 获取相关笔记
        note_manager = await get_context_notes(self.session.session_id)
        notes, notes_from_other_group = await note_manager.filter_note(chat_history)

        # 获取用户 profile 信息
        user_profiles = await self._get_user_profiles()

        # 格式化 profile 信息
        if user_profiles:
            profiles_text = "\n".join(user_profiles)
        else:
            profiles_text = await self.session.text("prompt.profile.none")

        async def format_note(note):
            created_time = datetime.fromtimestamp(note.created_time).strftime("%y-%m-%d")
            return await self.session.text("prompt.note.format", note.content, note.id, created_time)

        return generate_message(
            await self.session.text(
                "prompt_group.default",
                (
                    "\n".join([await format_note(note) for note in notes])
                    if notes
                    else await self.session.text("prompt.note.none")
                ),
                datetime.now().isoformat(),
                self.session.session_name,
                (
                    "\n".join([await format_note(note) for note in notes_from_other_group])
                    if notes_from_other_group
                    else await self.session.text("prompt.note.none")
                ),
                profiles_text,
            ),
            "system",
        )

    async def handle_recall(self, message_id: str, message_content: str) -> None:
        self.openai_messages.append_user_message(
            await self.session.text(
                "prompt.recall",
                datetime.now().strftime("%H:%M:%S"),
                message_id,
                message_content,
            )
        )

    async def handle_poke(self, operator_name: str, target_name: str, to_me: bool) -> None:
        if to_me:
            self.openai_messages.append_user_message(
                await self.session.text("prompt.poke.to_me", datetime.now().strftime("%H:%M:%S"), operator_name)
            )
            self.blocked = False
            await self.generate_reply(True)
            self.blocked = True
        else:
            self.openai_messages.append_user_message(
                await self.session.text(
                    "prompt.poke.to_other",
                    datetime.now().strftime("%H:%M:%S"),
                    operator_name,
                    target_name,
                )
            )

    async def handle_reaction(self, message_string: str, operator_name: str, emoji_id: str) -> None:
        self.openai_messages.append_user_message(
            await self.session.text(
                "prompt.reaction",
                datetime.now().strftime("%H:%M:%S"),
                operator_name,
                message_string,
                QQ_EMOJI_MAP[emoji_id],
            )
        )
        await self.generate_reply(False)


from nonebot_plugin_ghot.function import get_group_hot_score


class BaseSession(ABC):

    def __init__(self, session_id: str, bot: Bot, target: Target, lang_str: str = f"mlsid::--lang=zh_hans") -> None:
        self.session_id = session_id
        self.target = target
        self.bot = bot
        self.lang_str = lang_str
        self.tool_calls_history = []
        self.message_queue: list[tuple[UniMessage, Event, T_State, str, str, datetime, bool, str]] = []
        self.cached_messages: list[CachedMessage] = []
        self.message_cache_counter = 0
        self.ghot_coefficient = 1
        self.accumulated_text_length = 0  # 累计文本长度
        self.last_activate = datetime.now()
        self.mute_until: Optional[datetime] = None
        self.group_users: dict[str, str] = {}
        self.session_name = "未命名会话"
        self.llm_timers = []  # 定时器列表
        self.pending_interactions: dict[str, PendingInteraction] = {}  # 待处理的交互请求
        self.processor = MessageProcessor(self)

    @abstractmethod
    async def setup(self) -> None:
        await self.processor.setup()

    @abstractmethod
    def is_napcat_bot(self) -> bool:
        pass

    @abstractmethod
    async def send_poke(self, target_id: str) -> None:
        pass

    async def get_probability(self, length_adjustment: int = 0, apply_ghot_coeefficient: bool = True) -> float:
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

        # 应用好感度系数
        if len(self.cached_messages) > 0:
            avg_fav = sum(
                [(await get_user(msg["user_id"])).get_fav() for msg in self.cached_messages if not msg["self"]]
            ) / len(self.cached_messages)
            logger.debug(f"{avg_fav=}")
            final_probability *= 1 + 0.8 * (1 - math.e ** (-5 * avg_fav))

        # 确保概率在 0.0-1.0 之间
        return max(0.0, min(1.0, final_probability))

    @abstractmethod
    async def calculate_ghot_coefficient(self) -> None:
        pass

    def clean_cached_message(self) -> None:
        if len(self.cached_messages) > 50:
            self.cached_messages = self.cached_messages[-50:]

    async def on_cache_posted(self) -> None:
        self.message_cache_counter += 1
        await self.calculate_ghot_coefficient()
        self.clean_cached_message()
        if self.message_cache_counter % 50 == 0:
            await self.setup_session_name()
        self.last_activate = datetime.now()

    async def mute(self) -> None:
        self.mute_until = datetime.now() + timedelta(minutes=15)

    @abstractmethod
    async def setup_session_name(self) -> None:
        pass

    async def handle_message(
        self, message: UniMessage, user_id: str, event: Event, state: T_State, nickname: str, mentioned: bool = False
    ) -> None:
        message_id = get_message_id(event)
        self.message_queue.append((message, event, state, user_id, nickname, datetime.now(), mentioned, message_id))

    @abstractmethod
    async def format_message(self, origin_message: str) -> UniMessage:
        pass

    async def _get_users_in_cached_message(self) -> dict[str, str]:
        users = {}
        for message in self.cached_messages:
            if not message["self"]:
                users[message["nickname"]] = message["user_id"]
        return users

    @abstractmethod
    async def get_users(self) -> dict[str, str]:
        pass

    @abstractmethod
    async def get_user_info(self, user_id: str) -> AdapterUserInfo:
        pass

    async def handle_poke(self, event: PokeNotifyEvent, nickname: str) -> None:
        user = await get_user(str(event.target_id))
        target_nickname = await get_nickname(user.user_id, self.bot, event)
        await self.processor.handle_poke(nickname, target_nickname, event.is_tome())

    def create_pending_interaction(self, user_id: str, nickname: str, action: RuaAction) -> str:
        """创建一个待处理的交互请求，返回交互 ID"""
        interaction_id = str(uuid.uuid4())[:8]  # 使用短 UUID
        self.pending_interactions[interaction_id] = PendingInteraction(
            interaction_id=interaction_id,
            user_id=user_id,
            nickname=nickname,
            action=action,
            created_at=datetime.now().timestamp(),
        )
        return interaction_id

    async def text(self, key: str, *args, **kwargs) -> str:
        return await lang.text(key, self.lang_str, *args, **kwargs)

    def remove_pending_interaction(self, interaction_id: str) -> Optional[PendingInteraction]:
        """移除并返回待处理的交互请求"""
        return self.pending_interactions.pop(interaction_id, None)

    def cleanup_expired_interactions(self, max_age_seconds: int = 300) -> int:
        """清理过期的交互请求（默认5分钟过期）"""
        now = datetime.now().timestamp()
        expired_ids = [
            interaction_id
            for interaction_id, interaction in self.pending_interactions.items()
            if now - interaction["created_at"] > max_age_seconds
        ]
        for interaction_id in expired_ids:
            self.pending_interactions.pop(interaction_id, None)
        return len(expired_ids)

    async def handle_rua(self, nickname: str, user_id: str, action: RuaAction) -> None:
        """
        处理 rua 互动事件

        Args:
            nickname: 发起互动的用户昵称
            user_id: 发起互动的用户 ID
            action: 选择的 rua 动作
        """
        action_name = action["name"]

        # 生成事件提示
        event_prompt = await lang.text(f"rua.actions.{action_name}.prompt", self.lang_str, nickname)

        # 如果该动作可以被拒绝，生成交互 ID 并添加拒绝提示
        if action["refusable"]:
            interaction_id = self.create_pending_interaction(user_id=user_id, nickname=nickname, action=action)
            refusable_hint = await lang.text("rua.refusable_hint", self.lang_str, interaction_id)
            event_prompt = f"{event_prompt}\n{refusable_hint}"

        # 向会话发送事件，强制触发回复
        await self.post_event(event_prompt, "all")

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

        await self.processor.openai_messages.save_to_db()

    async def get_cached_messages_string(self) -> str:
        messages = []
        for message in self.cached_messages:
            messages.append(
                f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]: {message['content']}"
            )
        return "\n".join(messages)

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
        timer_id = f"{self.session_id}_{now.timestamp()}"

        # 存储定时器信息
        self.llm_timers.append({"id": timer_id, "trigger_time": trigger_time, "description": description})

        return await self.text("timer.set", delay)

    async def post_event(self, event_prompt: str, trigger_mode: Literal["none", "probability", "all"]) -> None:
        """
        向消息队列中添加一个事件的文本

        Args:
            event_prompt: 事件的描述文本
            trigger_mode: 触发模式
                - "none": 不触发回复
                - "probability": 使用概率计算判断是否触发回复
                - "all": 强制触发回复
        """
        # 添加事件消息到消息队列
        content = await self.text("prompt.event_template", datetime.now().strftime("%H:%M:%S"), event_prompt)
        self.processor.openai_messages.append_user_message(content)

        # 根据触发模式决定是否生成回复
        if trigger_mode == "none":
            return
        await self.processor.generate_reply(force_reply=trigger_mode == "all")


class PrivateSession(BaseSession):

    def __init__(self, session_id: str, bot: Bot, target: Target) -> None:
        super().__init__(session_id, bot, target, lang_str=session_id)
        self.nickname = ""
        self.call = "你"
        self.user_info: AdapterUserInfo

    async def setup(self) -> None:
        await super().setup()
        await self.setup_session_name()

    async def setup_session_name(self) -> None:
        ml_user = await get_user(self.session_id)
        if isinstance(self.bot, OB11Bot):
            user_info = await self.bot.get_stranger_info(user_id=int(self.session_id))
            if ml_user.has_nickname():
                self.nickname = ml_user.get_nickname()
            else:
                self.nickname = user_info["nickname"]
            self.user_info = AdapterUserInfo(
                nickname=self.nickname, sex=user_info["sex"], role="user", join_time=0, card=None
            )
        else:
            self.nickname = ml_user.get_nickname()
            self.user_info = AdapterUserInfo(nickname=self.nickname, sex="unknown", role="user", join_time=0, card=None)
        self.call = ml_user.get_config_key("call", self.nickname)
        self.session_name = f"与 {self.nickname} 的私聊"

    async def format_message(self, origin_message: str) -> UniMessage:
        return UniMessage().text(text=origin_message.replace(f"@{self.nickname}", self.call))

    def is_napcat_bot(self) -> bool:
        return self.bot.self_id in config.napcat_bot_ids

    async def send_poke(self, _: str) -> None:
        if isinstance(self.bot, OB11Bot):
            await self.bot.call_api("friend_poke", user_id=self.session_id)

    async def calculate_ghot_coefficient(self) -> int:
        self.ghot_coefficient = 100
        return 100

    async def get_user_info(self, _: str) -> AdapterUserInfo:
        return self.user_info

    async def get_users(self) -> dict[str, str]:
        return {}


class GroupSession(BaseSession):

    async def get_user_info(self, user_id: str) -> AdapterUserInfo:
        if isinstance(self.bot, OB11Bot):
            member_info = await self.bot.get_group_member_info(
                group_id=int(self.adapter_group_id), user_id=int(user_id)
            )
            return AdapterUserInfo(**member_info)
        cached_users = await self.get_users()
        if user_id in cached_users.values():
            for nickname, uid in cached_users.items():
                if uid == user_id:
                    return AdapterUserInfo(nickname=nickname, sex="unknown", role="member", join_time=0, card=None)
        return AdapterUserInfo(
            nickname=(await get_user(user_id)).get_nickname(), sex="unknown", role="member", join_time=0, card=None
        )

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

    def __init__(self, session_id: str, bot: Bot, target: Target, lang_name: str = "zh_hans") -> None:
        lang_str = f"mlsid::--lang={lang_name}"
        super().__init__(session_id, bot, target, lang_str)
        self.adapter_group_id = target.id
        self.cached_latest_message = None

    async def setup(self) -> None:
        await super().setup()
        await self.setup_session_name()
        await self.calculate_ghot_coefficient()

    async def send_poke(self, target_id: str) -> None:
        await self.bot.call_api("group_poke", group_id=int(self.adapter_group_id), user_id=int(target_id))

    def is_napcat_bot(self) -> bool:
        return self.bot.self_id in config.napcat_bot_ids

    async def calculate_ghot_coefficient(self) -> None:
        self.ghot_coefficient = round(max((15 - (await get_group_hot_score(self.session_id))[2]) * 0.8, 1))
        cached_users = set()
        for message in self.cached_messages[:-5]:
            if not message["self"]:
                cached_users.add(message["user_id"])
        if len(cached_users) <= 1:
            self.ghot_coefficient *= 0.75

    async def setup_session_name(self) -> None:
        if isinstance(self.bot, OB11Bot):
            self.session_name = (await self.bot.get_group_info(group_id=int(self.adapter_group_id)))["group_name"]

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

    async def process_timer(self) -> None:
        await super().process_timer()
        dt = datetime.now()
        if self.processor.blocked or not self.cached_messages:
            return
        time_to_last_message = (dt - self.cached_messages[-1]["send_time"]).total_seconds()
        if (
            30 < time_to_last_message
            and not self.cached_messages[-1]["self"]
            and self.cached_messages[-1] is not self.cached_latest_message
        ):
            self.cached_latest_message = self.cached_messages[-1]
            asyncio.create_task(self.processor.generate_reply(True))


from ..config import config

groups: dict[str, BaseSession] = {}


def get_group_session(group_id: str) -> BaseSession:
    """
    获取指定群组的 GroupSession 对象

    Args:
        group_id: 群组 ID

    Returns:
        GroupSession 对象

    Raises:
        KeyError: 当群组 Session 不存在时
    """
    return groups[group_id]


async def post_group_event(
    group_id: str, event_prompt: str, trigger_mode: Literal["none", "probability", "all"]
) -> bool:
    """
    向指定群组发送事件

    Args:
        group_id: 群组 ID
        event_prompt: 事件的描述文本
        trigger_mode: 触发模式
            - "none": 不触发回复
            - "probability": 使用概率计算判断是否触发回复
            - "all": 强制触发回复

    Returns:
        bool: 是否成功执行
    """
    try:
        session = get_group_session(group_id)
        await session.post_event(event_prompt, trigger_mode)
        return True
    except KeyError:
        return False


async def get_private_session(user_id: str, target: Target, bot: Bot) -> PrivateSession:
    if user_id not in groups:
        groups[user_id] = PrivateSession(user_id, bot, target)
        await groups[user_id].setup()
    return cast(PrivateSession, groups[user_id])


@on_message(priority=50, rule=enabled_group, block=False).handle()
async def _(
    event: Event,
    matcher: Matcher,
    bot: Bot,
    state: T_State,
    user_id: str = get_user_id(),
    session_id: str = get_group_id(),
) -> None:
    if isinstance(bot, BotQQ):
        await matcher.finish()
    elif session_id not in groups:
        groups[session_id] = GroupSession(session_id, bot, get_target(event))
        await groups[session_id].setup()
    elif groups[session_id].mute_until is not None:
        await matcher.finish()
    plaintext = event.get_plaintext().strip()
    if any([plaintext.startswith(p) for p in config.command_start]):
        await matcher.finish()
    platform_message = event.get_message()
    message = await UniMessage.of(message=platform_message, bot=bot).attach_reply(event, bot)
    nickname = await get_nickname(user_id, bot, event)
    await groups[session_id].handle_message(message, user_id, event, state, nickname, event.is_tome())


async def get_group_session_forced(group_id: str, target: Target, bot: Bot) -> GroupSession:
    if group_id not in groups:
        groups[group_id] = GroupSession(group_id, bot, target)
        await groups[group_id].setup()
    return cast(GroupSession, groups[group_id])


@on_message(priority=50, rule=private_message, block=False).handle()
async def _(
    event: Event,
    matcher: Matcher,
    bot: Bot,
    state: T_State,
    user_id: str = get_user_id(),
) -> None:
    session_id = user_id
    if isinstance(bot, BotQQ):
        await matcher.finish()
    elif session_id not in groups:
        groups[session_id] = PrivateSession(session_id, bot, get_target(event))
        await groups[session_id].setup()
    elif groups[session_id].mute_until is not None:
        await matcher.finish()
    plaintext = event.get_plaintext().strip()
    if any([plaintext.startswith(p) for p in config.command_start]):
        # TODO 避免与 cave 冲突
        await matcher.finish()
    platform_message = event.get_message()
    message = await UniMessage.of(message=platform_message, bot=bot).attach_reply(event, bot)
    nickname = await get_nickname(user_id, bot, event)
    await groups[session_id].handle_message(message, user_id, event, state, nickname, True)


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
        probability = await session.get_probability(apply_ghot_coeefficient=False)
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

    async def handle_block(self) -> None:
        if len(self.argv) < 2:
            await lang.finish("command.no_argv", self.user_id)

        target_type = self.argv[1]

        if target_type == "user":
            if len(self.argv) < 3:
                await lang.finish("command.no_argv", self.user_id)
            action = self.argv[2]
            blocked_list = json.loads(self.group_config.blocked_user)

            if action == "list":
                await lang.finish("command.block.user.list", self.user_id, ", ".join(blocked_list))

            if len(self.argv) < 4:
                await lang.finish("command.no_argv", self.user_id)
            target_id = self.argv[3]

            if action == "add":
                if target_id not in blocked_list:
                    blocked_list.append(target_id)
                    self.group_config.blocked_user = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.user.added", self.user_id, target_id)
                else:
                    await lang.finish("command.block.user.exists", self.user_id, target_id)
            elif action == "remove":
                if target_id in blocked_list:
                    blocked_list.remove(target_id)
                    self.group_config.blocked_user = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.user.removed", self.user_id, target_id)
                else:
                    await lang.finish("command.block.user.not_found", self.user_id, target_id)

        elif target_type == "keyword":
            if len(self.argv) < 3:
                await lang.finish("command.no_argv", self.user_id)
            action = self.argv[2]
            blocked_list = json.loads(self.group_config.blocked_keyword)

            if action == "list":
                await lang.finish("command.block.keyword.list", self.user_id, ", ".join(blocked_list))

            if len(self.argv) < 4:
                await lang.finish("command.no_argv", self.user_id)
            target_keyword = self.argv[3]

            if action == "add":
                if target_keyword not in blocked_list:
                    blocked_list.append(target_keyword)
                    self.group_config.blocked_keyword = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.keyword.added", self.user_id, target_keyword)
                else:
                    await lang.finish("command.block.keyword.exists", self.user_id, target_keyword)
            elif action == "remove":
                if target_keyword in blocked_list:
                    blocked_list.remove(target_keyword)
                    self.group_config.blocked_keyword = json.dumps(blocked_list)
                    await self.merge_group_config()
                    await lang.finish("command.block.keyword.removed", self.user_id, target_keyword)
                else:
                    await lang.finish("command.block.keyword.not_found", self.user_id, target_keyword)
        else:
            await lang.finish("command.no_argv", self.user_id)

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
            case "block":
                await self.handle_block()
            case _:
                await lang.finish("command.no_argv", self.user_id)

    async def get_group_session(self) -> BaseSession:
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
    # 清理过期的交互请求
    total_expired_count = 0
    for session in groups.values():
        expired_count = session.cleanup_expired_interactions()
        total_expired_count += expired_count
    logger.debug(f"Will clean up {total_expired_count} expired session.")

    expired_session_id = []
    for session_id, session in groups.items():
        logger.debug(f"Triggering timer from {session_id=}.")
        await session.process_timer()
        if isinstance(session, PrivateSession) and (datetime.now() - session.last_activate) >= timedelta(minutes=15):
            expired_session_id.append(session_id)
    for session_id in expired_session_id:
        session = groups[session_id]
        await session.processor.openai_messages.save_to_db()
        groups.pop(session_id)
        logger.info(f"Session {session_id} expired and removed.")


@scheduler.scheduled_job("cron", hour="3", id="cleanup_expired_notes")
async def _() -> None:
    """Daily cleanup of expired notes at 3 AM"""
    from ..utils.note_manager import cleanup_expired_notes

    deleted_count = await cleanup_expired_notes()
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} expired notes")


@on_notice(block=False).handle()
async def _(event: GroupRecallNoticeEvent, group_id: str = get_group_id()) -> None:
    message_id = str(event.message_id)
    if group_id not in groups:
        return
    session = groups[group_id]
    await session.handle_recall(message_id)


@on_notice(block=False).handle()
async def _(
    event: PokeNotifyEvent,
    bot: Bot,
    moonlark_group_id: str = get_group_id(),
    user_id: str = get_user_id(),
) -> None:
    if moonlark_group_id not in groups:
        return
    session = groups[moonlark_group_id]
    nickname = await get_nickname(user_id, bot, event)
    await session.handle_poke(event, nickname)


async def group_msg_emoji_like(event: NoticeEvent) -> bool:
    logger.info(result := event.notice_type == "group_msg_emoji_like")
    return result


@on_notice(rule=group_msg_emoji_like, block=False).handle()
async def _(event: NoticeEvent, bot: OB11Bot, platform_id: str = get_group_id()) -> None:
    event_dict = event.model_dump()
    group_id = f"{platform_id}_{event_dict['group_id']}"
    user_id = await get_main_account(str(event_dict["user_id"]))
    if group_id not in groups:
        return
    session = groups[group_id]
    message = await parse_message_to_string(
        await parse_dict_message((await bot.get_msg(message_id=event_dict["message_id"]))["message"], bot),
        event,
        bot,
        {},
    )
    user = await get_user(user_id)
    if user.has_nickname():
        operator_nickname = user.nickname
    else:
        user_info = await bot.get_group_member_info(group_id=event_dict["group_id"], user_id=int(user_id))
        operator_nickname = user_info["card"] or user_info["nickname"]
    emoji_id = event_dict["likes"][0]["emoji_id"]
    logger.debug(f"emoji like: {emoji_id} {message} {operator_nickname}")
    await session.processor.handle_reaction(message, operator_nickname, emoji_id)


@on_notice(block=False).handle()
async def _(event: FriendRecallNoticeEvent, user_id: str = get_user_id()) -> None:
    message_id = str(event.message_id)
    session = groups[user_id]
    await session.handle_recall(message_id)


@get_driver().on_shutdown
async def _() -> None:
    for session in groups.values():
        await session.processor.openai_messages.save_to_db()
