import asyncio
import math
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Callable, Iterable, Literal, Optional, TypeAlias, overload

from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.log import logger
from nonebot.typing import T_State
from nonebot_plugin_alconna import At, Target, Text, UniMessage, get_message_id
from nonebot_plugin_larkuser import get_nickname, get_user
from nonebot_plugin_orm import get_session
from sqlalchemy import delete

from nonebot_plugin_chat.lang import lang
from nonebot_plugin_chat.types import AdapterUserInfo, CachedMessage, PendingInteraction, RuaAction
from nonebot_plugin_chat.utils.trigger import calculate_trigger_probability

from ...models import Timer

# 消息队列项类型定义
MessageQueueItem: TypeAlias = (
    tuple[Literal["message"], tuple[UniMessage, Event, T_State, str, str, datetime, bool, str, str]]
    | tuple[Literal["event"], tuple[str, Literal["probability", "none", "all"]]]
)

# 用户未设置任何昵称时的默认展示名前缀（见 nonebot_plugin_larkuser.utils.nickname.get_nickname）
ANONYMOUS_NICKNAME_PREFIX = "匿名-"


def get_anonymous_default_nickname(user_id: str) -> str:
    """获取用户 ID 为 ``user_id`` 时的匿名默认展示名"""
    return f"{ANONYMOUS_NICKNAME_PREFIX}{user_id[-4:]}"


def build_anonymous_mention_pattern(suffixes: Iterable[str]) -> re.Pattern[str]:
    """构建匿名用户提及的匹配正则

    完整形式 ``匿名-XXXX`` 允许带 ``@`` 前缀出现，末尾不能紧跟字母数字（避免截断
    更长的编号）；裸形式 ``XXXX`` 只在前后都不是字母数字或连字符时匹配，防止把普通
    文本中的数字片段当成对匿名用户的引用。
    """
    alternatives = "|".join(sorted((re.escape(suffix) for suffix in suffixes), key=len, reverse=True))
    return re.compile(
        rf"@?{re.escape(ANONYMOUS_NICKNAME_PREFIX)}(?:{alternatives})(?![0-9A-Za-z])"
        rf"|@?(?<![0-9A-Za-z-])(?:{alternatives})(?![0-9A-Za-z])"
    )


def split_text_by_anonymous_suffix(
    text: str,
    pattern: re.Pattern[str],
    suffix_map: dict[str, str],
) -> list[tuple[str, Optional[str]]]:
    """按匿名用户提及切分文本

    返回 ``(内容, 提及目标)`` 序列：普通文本的提及目标为 ``None``，命中匿名用户的
    部分则为对应的用户 ID。
    """
    parts: list[tuple[str, Optional[str]]] = []
    cursor = 0
    for match in pattern.finditer(text):
        token = match.group(0).removeprefix("@").removeprefix(ANONYMOUS_NICKNAME_PREFIX)
        target = suffix_map.get(token)
        if target is None:
            continue
        if match.start() > cursor:
            parts.append((text[cursor : match.start()], None))
        parts.append((match.group(0), target))
        cursor = match.end()
    if cursor < len(text):
        parts.append((text[cursor:], None))
    return parts


def parse_anonymous_mentions(message: UniMessage, suffix_map: dict[str, str]) -> UniMessage:
    """把消息文本中的匿名用户提及（``匿名-XXXX`` 或裸 ``XXXX``）解析为 At 段

    仅处理文本段，其他段（图片、原有的 At 等）原样保留；上下文中没有出现过的
    匿名后缀不会被匹配。
    """
    if not suffix_map or not any(isinstance(segment, Text) for segment in message):
        return message
    pattern = build_anonymous_mention_pattern(suffix_map)
    result = UniMessage()
    for segment in message:
        if not isinstance(segment, Text):
            result.append(segment)
            continue
        for text, target in split_text_by_anonymous_suffix(segment.text, pattern, suffix_map):
            if target is None:
                result.append(Text(text))
            else:
                result.append(At("user", target))
    return result


class SessionQueue:
    def __init__(self, on_item_queued: Callable[[], None]) -> None:
        self._items: list[MessageQueueItem] = []
        self._on_item_queued = on_item_queued

    def append(self, item: MessageQueueItem) -> None:
        self._items.append(item)
        self._on_item_queued()

    def pop(self, index: int = 0) -> MessageQueueItem:
        return self._items.pop(index)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)


from ..processor import MessageProcessor


class BaseSession(ABC):
    @staticmethod
    @abstractmethod
    def get_session_type() -> Literal["private", "group"]: ...

    def __init__(self, session_id: str, bot: Bot, target: Target, lang_str: str = "mlsid::--lang=zh_hans") -> None:
        self.session_id = session_id
        self.target = target
        self.bot = bot
        self.lang_str = lang_str
        self.tool_calls_history = []
        self.message_cache_counter = 0
        self.ghot_coefficient = 1
        self.accumulated_text_length = 0  # 累计文本长度
        self.last_activate = datetime.now()
        self.mute_until: Optional[datetime] = None
        self.group_users: dict[str, str] = {}
        self.llm_timers = []  # 定时器列表
        self.pending_interactions: dict[str, PendingInteraction] = {}  # 待处理的交互请求
        self.last_interest: Optional[float] = None  # 缓存的 interest 值
        self.last_interest_update_time: Optional[datetime] = None  # interest 最后更新时间
        self.processor = MessageProcessor(self)
        self.message_queue = SessionQueue(self.processor.notify_message_queued)

    @property
    def cached_messages(self) -> list[CachedMessage]:
        """会话的消息列表（由 Chat Context 持有，这里只做转发）"""
        return self.processor.openai_messages.context.cached_messages

    # interest 衰减配置
    INTEREST_HALF_LIFE = 420  # 半衰期（秒），默认 7 分钟
    INTEREST_CENTER = 0.5  # 回正中心值

    def set_target(self, target: Target, bot: Bot) -> None:
        self.target = target
        self.bot = bot

    @abstractmethod
    async def setup(self) -> None:
        await self.processor.setup()
        await self.restore_timers()

    @abstractmethod
    def is_napcat_bot(self) -> bool:
        pass

    @abstractmethod
    async def send_poke(self, target_id: str) -> None:
        pass

    async def get_probability_details(self, length_adjustment: int = 0) -> dict:
        """
        计算触发回复的概率并返回详细信息

        参数:
            length_adjustment: 对累计文本长度的调整值，默认为0

        返回:
            包含概率计算详情的字典:
            - accumulated_length: 当前累计文本长度
            - base_probability: 基础触发概率 (0.0-0.95)
            - ghot_coefficient: 群热度分数系数
            - ghot_applied: 应用热度系数后的概率
            - favorability_coefficient: 好感度系数
            - interest_coefficient: 兴趣系数 (interest=0 -> 0.25, interest=1 -> 4)
            - interest_value: 当前兴趣值 (0-1, 可能为 None)
            - final_probability: 最终触发概率 (0.0-1.0)
        """
        # 使用调整后的累计文本长度
        adjusted_length = self.accumulated_text_length + length_adjustment

        # 使用 calculate_trigger_probability 函数计算基础概率
        base_probability = calculate_trigger_probability(adjusted_length)

        # 应用热度系数
        ghot_applied = base_probability * self.ghot_coefficient

        # 计算好感度系数
        favorability_coefficient = 1.0
        if len(self.cached_messages) > 0:
            avg_fav = sum(
                [(await get_user(msg["user_id"])).get_fav() for msg in self.cached_messages if not msg["self"]],
            ) / len(self.cached_messages)
            logger.debug(f"{avg_fav=}")
            favorability_coefficient = 1 + 0.8 * (1 - math.e ** (-5 * avg_fav))

        # 计算 interest 系数映射 (0-1) -> (0.25-4)
        interest_coefficient = 1.0
        # 应用时间衰减获取回正后的 interest 值
        decayed_interest = self._get_decayed_interest()
        interest_value = decayed_interest
        if decayed_interest is not None:
            interest_coefficient = 0.25 + decayed_interest * 3.75
            logger.debug(
                f"Applied interest coefficient: {interest_coefficient:.2f} "
                f"(raw={self.last_interest:.2f}, decayed={decayed_interest:.2f})",
            )

        # 计算最终概率
        final_probability = ghot_applied * favorability_coefficient * interest_coefficient

        return {
            "accumulated_length": adjusted_length,
            "base_probability": base_probability,
            "ghot_coefficient": self.ghot_coefficient,
            "ghot_applied": ghot_applied,
            "favorability_coefficient": favorability_coefficient,
            "interest_coefficient": interest_coefficient,
            "interest_value": interest_value,
            "final_probability": max(0.0, min(1.0, final_probability)),
        }

    async def get_probability(self, length_adjustment: int = 0) -> float:
        """
        计算触发回复的概率

        参数:
            length_adjustment: 对累计文本长度的调整值，默认为0

        返回:
            触发回复的概率值（0.0-1.0之间）
        """
        details = await self.get_probability_details(length_adjustment)
        return details["final_probability"]

    def _get_decayed_interest(self) -> Optional[float]:
        """获取经过时间衰减后的 interest 值"""
        if self.last_interest is None or self.last_interest_update_time is None:
            return self.last_interest
        elapsed = (datetime.now() - self.last_interest_update_time).total_seconds()
        if elapsed <= 0:
            return self.last_interest
        # 指数衰减公式：向中心值回正
        # decayed = center + (original - center) * 0.5 ^ (elapsed / half_life)
        decay_factor = math.pow(0.5, elapsed / self.INTEREST_HALF_LIFE)
        decayed = self.INTEREST_CENTER + (self.last_interest - self.INTEREST_CENTER) * decay_factor
        logger.debug(
            f"Interest decay: {self.last_interest:.2f} -> {decayed:.2f} "
            f"(elapsed={elapsed:.0f}s, factor={decay_factor:.4f})",
        )
        return decayed

    def set_interest(self, interest: Optional[float]) -> None:
        """缓存 interest 值用于后续概率计算"""
        self.last_interest = interest
        if interest is not None:
            self.last_interest_update_time = datetime.now()

    @abstractmethod
    async def calculate_ghot_coefficient(self) -> None:
        pass

    async def on_cache_posted(self) -> None:
        self.message_cache_counter += 1
        await self.calculate_ghot_coefficient()
        self.last_activate = datetime.now()

    async def mute(self) -> None:
        self.mute_until = datetime.now() + timedelta(minutes=15)

    @abstractmethod
    async def get_session_name(self) -> str:
        pass

    async def handle_message(
        self,
        message: UniMessage,
        user_id: str,
        event: Event,
        state: T_State,
        nickname: str,
        mentioned: bool = False,
        platform_user_id: str = "",
    ) -> None:
        message_id = get_message_id(event)
        if not platform_user_id:
            platform_user_id = user_id
        self.message_queue.append(
            (
                "message",
                (message, event, state, user_id, nickname, datetime.now(), mentioned, message_id, platform_user_id),
            ),
        )

    async def add_event(
        self,
        event_prompt: str,
        trigger_mode: Literal["probability", "none", "all"] = "probability",
    ) -> None:
        """向消息队列中添加一个事件

        Args:
            event_prompt: 事件的描述文本
            trigger_mode: 触发模式
                - "none": 不触发回复
                - "probability": 使用概率计算判断是否触发回复
                - "all": 强制触发回复
        """
        self.message_queue.append(("event", (event_prompt, trigger_mode)))

    @abstractmethod
    async def format_message(self, origin_message: str) -> UniMessage:
        pass

    async def _get_users_in_cached_message(self) -> dict[str, str]:
        users = {}
        for message in self.cached_messages:
            if not message["self"]:
                users[message["nickname"]] = message.get("platform_user_id", message["user_id"])
        return users

    def _get_anonymous_users(self) -> dict[str, str]:
        """收集上下文中出现过的匿名用户，返回「匿名后缀 -> 适配器原始用户 ID」的映射

        匿名指用户没有设置昵称、在上下文里以默认名 ``匿名-XXXX``（``XXXX`` 为主账号
        ID 的末 4 位）出现。此时模型在回复中可能写出 ``匿名-XXXX`` 或直接引用 ``XXXX``，
        发送前需要把它们还原成对真实用户的 At。
        """
        users: dict[str, str] = {}
        for message in self.cached_messages:
            if message.get("self"):
                continue
            user_id = message.get("user_id", "")
            platform_user_id = message.get("platform_user_id") or user_id
            nickname = message.get("nickname", "")
            if not user_id or not platform_user_id or nickname != get_anonymous_default_nickname(user_id):
                continue
            users[user_id[-4:]] = platform_user_id
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

    def create_pending_interaction(
        self,
        user_id: str,
        nickname: str,
        action: RuaAction,
        message_id: str = "",
    ) -> str:
        """创建一个待处理的交互请求，返回交互 ID"""
        interaction_id = str(uuid.uuid4())[:8]  # 使用短 UUID
        self.pending_interactions[interaction_id] = PendingInteraction(
            interaction_id=interaction_id,
            user_id=user_id,
            nickname=nickname,
            action=action,
            created_at=datetime.now().timestamp(),
            message_id=message_id,
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

    async def handle_rua(self, nickname: str, user_id: str, action: RuaAction, message_id: str) -> None:
        """
        处理 rua 互动事件

        Args:
            nickname: 发起互动的用户昵称
            user_id: 发起互动的用户 ID
            action: 选择的 rua 动作
            message_id: 触发 rua 命令的消息 ID，用于 reaction 和回复
        """

        action_name = action["name"]

        # 生成事件提示
        event_prompt = await lang.text(f"rua.actions.{action_name}.prompt", self.lang_str, nickname)

        # 添加供回复的消息 ID
        reply_hint = await lang.text("rua.reply_hint", self.lang_str, message_id)
        event_prompt = f"{event_prompt}\n{reply_hint}"

        # 如果该动作可以被拒绝，生成交互 ID 并添加拒绝提示
        if action["refusable"]:
            interaction_id = self.create_pending_interaction(
                user_id=user_id,
                nickname=nickname,
                action=action,
                message_id=message_id,
            )
            refusable_hint = await lang.text("rua.refusable_hint", self.lang_str, interaction_id)
            event_prompt = f"{event_prompt}\n{refusable_hint}"

        # 向会话发送事件，强制触发回复
        await self.post_event(event_prompt, "all")

    async def change_sleep_status(
        self,
        deal_type: Literal["ready", "delay"],
        delay_minutes: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> str:
        """
        修改睡觉状态

        Args:
            deal_type: 决策类型，"ready"表示准备睡觉，"delay"表示延迟
            delay_minutes: 延迟的分钟数（仅当deal_type为"delay"时有效）
            reason: 延迟的原因（仅当deal_type为"delay"时有效）

        Returns:
            工具调用的结果（会等待main_session统一处理）
        """
        from ..ego import moonlark_main

        # 验证参数
        if deal_type == "delay":
            if delay_minutes is None:
                delay_minutes = 0
            if delay_minutes > 30:
                delay_minutes = 30
            if delay_minutes < 0:
                delay_minutes = 0

        # 创建一个Future用于等待moonlark_main的处理结果
        # 这里使用异步等待挂起响应
        result_future = asyncio.get_event_loop().create_future()

        # 提交决策到moonlark_main
        await moonlark_main.submit_sleep_decision(
            session_id=self.session_id,
            deal_type=deal_type,
            delay_minutes=delay_minutes,  # type: ignore
            reason=reason,  # type: ignore
            future=result_future,
        )

        # 等待main_session的处理结果
        try:
            result = await asyncio.wait_for(result_future, timeout=120)  # 最多等待2分钟
            return result
        except asyncio.TimeoutError:
            return await self.text("sleep_decision.timeout")

    async def process_timer(self) -> None:
        # 上下文恢复失败时定期重试（重试有间隔，不依赖是否有新消息）
        self.processor.ensure_startup()
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

        if triggered_timers:
            async with get_session() as db_session:
                await db_session.execute(
                    delete(Timer).where(
                        Timer.session_id == self.session_id,
                        Timer.trigger_time <= dt,
                    ),
                )
                await db_session.commit()

        await self.processor.openai_messages.save_to_db()

    async def restore_timers(self) -> None:
        """从数据库恢复未触发的定时器（重启后调用）"""
        async with get_session() as db_session:
            from sqlalchemy import select

            result = await db_session.execute(select(Timer).where(Timer.session_id == self.session_id))
            rows = result.scalars().all()
            for row in rows:
                timer_id = f"{self.session_id}_{row.trigger_time.timestamp()}"
                self.llm_timers.append(
                    {
                        "id": timer_id,
                        "trigger_time": row.trigger_time,
                        "description": row.description,
                    },
                )
            if rows:
                logger.info(f"Restored {len(rows)} timers for session {self.session_id}")

    async def get_cached_messages_string(
        self,
        length: int = 50,
        include_self_message: bool = False,
        exclude_content_prefixes: Optional[tuple[str, ...]] = None,
    ) -> str:
        messages = []
        for message in self.cached_messages:
            # 根据 include_self_message 参数决定是否包含自己的消息
            if not include_self_message and message.get("self", False):
                continue
            content = message.get("content", "")
            if exclude_content_prefixes and content.startswith(exclude_content_prefixes):
                continue
            messages.append(
                f"[{message['send_time'].strftime('%H:%M:%S')}][{message['nickname']}]: {content}",
            )
        # 只返回最近的 length 条消息
        return "\n".join(messages[-length:])

    async def handle_recall(self, message_id: str) -> None:
        for message in self.cached_messages:
            if message["message_id"] == message_id:
                message_content = message["content"]
                break
        else:
            message_content = await self.text("recall_fetch_failed")

        await self.processor.handle_recall(message_id, message_content)

    async def set_timer(self, delay: int, description: str) -> str:
        """在当前会话设置一个一次性定时器

        Args:
            delay: 延迟时间（分钟），到点后触发一次
            description: 留给触发时自己的完整指令，会作为触发事件的文本注入会话并强制回复

        Returns:
            给模型的确认信息，包含确切的触发时间
        """
        now = datetime.now()
        trigger_time = now + timedelta(minutes=delay)
        timer_id = f"{self.session_id}_{now.timestamp()}"

        timer_entry = {"id": timer_id, "trigger_time": trigger_time, "description": description}
        self.llm_timers.append(timer_entry)

        async with get_session() as db_session:
            db_session.add(
                Timer(
                    session_id=self.session_id,
                    trigger_time=trigger_time,
                    description=description,
                ),
            )
            await db_session.commit()

        return await self.text(
            "prompt.timer_set",
            trigger_time.strftime("%Y-%m-%d %H:%M"),
            description,
        )

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
        await self.add_event(event_prompt, trigger_mode)
