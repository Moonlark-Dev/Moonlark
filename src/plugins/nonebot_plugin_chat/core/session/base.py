from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.log import logger
from nonebot.typing import T_State
from nonebot_plugin_alconna import Target, UniMessage, get_message_id
from nonebot_plugin_chat.utils.trigger import calculate_trigger_probability
from nonebot_plugin_chat.lang import lang
from nonebot_plugin_chat.models import RuaAction
from nonebot_plugin_chat.types import AdapterUserInfo, CachedMessage, PendingInteraction, RuaAction
from nonebot_plugin_larkuser import get_nickname, get_user


import math
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Literal, Optional

from ..processor import MessageProcessor


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
        await self.processor.generate_reply(important=trigger_mode == "all")
