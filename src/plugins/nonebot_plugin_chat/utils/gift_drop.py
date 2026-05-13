import random
import time
from collections import deque
from typing import Optional

from nonebot import logger
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

    def __new__(cls) -> "GiftDropManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
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


async def handle_gift_drop(
    user_id: str,
    group_id: str,
    message_id: Optional[str],
    is_registered: bool,
    send_reaction,
) -> None:
    """
    处理礼物掉落逻辑

    Args:
        user_id: 用户 ID
        group_id: 群组 ID
        message_id: 消息 ID（用于添加 reaction）
        is_registered: 用户是否已注册
        send_reaction: 发送 reaction 的回调函数，接受 (message_id, emoji_id) 参数
    """
    if not is_registered:
        return

    from ..models import ChatGroup
    from nonebot_plugin_orm import get_session as get_db_session

    async with get_db_session() as db_session:
        group_config = await db_session.get(ChatGroup, {"group_id": group_id})
        if not group_config or not group_config.dropping_enabled:
            return

    drop_manager = get_gift_drop_manager()
    gift_id = await drop_manager.try_drop(user_id)
    if gift_id and message_id:
        await send_reaction(message_id, DROP_REACTION_EMOJI_ID)
