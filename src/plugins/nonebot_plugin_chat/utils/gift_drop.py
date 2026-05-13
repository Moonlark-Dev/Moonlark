import random
import time
from collections import deque
from typing import Optional

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_items.registry.registry import ResourceLocation
from nonebot_plugin_items.utils.get import get_item
from nonebot_plugin_bag.utils.bag import give_item

# 礼物掉落权重配置
GIFT_DROP_TABLE: list[tuple[str, float]] = [
    ("moonlark:dried_fish", 0.30),
    ("moonlark:yarn_ball", 0.20),
    ("moonlark:bell_collar", 0.15),
    ("moonlark:catnip_pouch", 0.15),
    ("moonlark:cat_teaser", 0.12),
    ("moonlark:cat_can", 0.08),
]

# 掉落配置
DROP_CHANCE = 0.04  # 每条消息 4% 概率
MAX_DROPS_PER_HOUR = 3  # 每小时全局最多掉落 3 件
DROP_REACTION_EMOJI_ID = "63"  # 玫瑰 reaction


class GiftDropManager:
    """全局礼物掉落管理器"""

    _instance: Optional["GiftDropManager"] = None
    _initialized: bool = False

    def __new__(cls) -> "GiftDropManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if GiftDropManager._initialized:
            return
        GiftDropManager._initialized = True
        self.drop_timestamps: deque[float] = deque()

    def _cleanup_old_timestamps(self) -> None:
        """清理超过 1 小时的旧时间戳"""
        now = time.time()
        while self.drop_timestamps and now - self.drop_timestamps[0] > 3600:
            self.drop_timestamps.popleft()

    def can_drop(self) -> bool:
        """检查是否可以掉落（全局每小时限制）"""
        self._cleanup_old_timestamps()
        return len(self.drop_timestamps) < MAX_DROPS_PER_HOUR

    def record_drop(self) -> None:
        """记录一次掉落"""
        self.drop_timestamps.append(time.time())

    def roll_drop(self) -> bool:
        """随机判断是否触发掉落"""
        return random.random() < DROP_CHANCE

    def select_gift(self) -> str:
        """根据权重随机选择一个礼物"""
        items, weights = zip(*GIFT_DROP_TABLE)
        return random.choices(items, weights=weights, k=1)[0]

    async def try_drop(self, user_id: str) -> Optional[str]:
        """
        尝试掉落礼物

        Args:
            user_id: 用户 ID

        Returns:
            掉落的礼物 location 字符串，未掉落返回 None
        """
        if not self.roll_drop():
            return None
        if not self.can_drop():
            return None

        gift_id = self.select_gift()
        namespace, path = gift_id.split(":", 1)
        location = ResourceLocation(namespace, path)

        stack = await get_item(location, user_id, count=1)
        await give_item(user_id, stack)

        self.record_drop()
        logger.info(f"Gift drop: user={user_id}, gift={gift_id}")
        return gift_id


def get_gift_drop_manager() -> GiftDropManager:
    """获取 GiftDropManager 单例实例"""
    return GiftDropManager()


async def handle_gift_drop(bot: Bot, event: Event, user_id: str, group_id: str, is_napcat_bot: bool) -> None:
    """
    处理礼物掉落逻辑

    Args:
        bot: Bot 实例
        event: 消息事件
        user_id: 用户 ID
        group_id: 群组 ID
        is_napcat_bot: 是否为 napcat bot
    """
    if not is_napcat_bot:
        return

    from ..models import ChatGroup
    from nonebot_plugin_orm import get_session as get_db_session
    from nonebot_plugin_larkuser import get_user

    # 检查用户是否已注册
    user = await get_user(user_id)
    if user.register_time is None:
        return

    # 检查群组是否启用掉落
    async with get_db_session() as db_session:
        group_config = await db_session.get(ChatGroup, {"group_id": group_id})
        if not group_config or not group_config.dropping_enabled:
            return

    # 尝试掉落
    drop_manager = get_gift_drop_manager()
    gift_id = await drop_manager.try_drop(user_id)
    if not gift_id:
        return

    # 添加 reaction
    message_id = getattr(event, "message_id", None)
    if message_id:
        try:
            await bot.call_api(
                "set_msg_emoji_like",
                message_id=str(message_id),
                emoji_id=DROP_REACTION_EMOJI_ID,
                set=True,
            )
        except Exception as e:
            logger.debug(f"Gift drop reaction failed: {e}")
