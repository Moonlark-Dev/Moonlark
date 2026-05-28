"""主动私聊决策控制器（EGO 内部）

负责在 request_think 中根据状态决策是否主动私聊。
实际发送逻辑调用 core/proactive_chat.py。

与 core/proactive_chat.py 的区别：
- 本模块：EGO 决策逻辑（什么时候该私聊、私聊谁）
- proactive_chat.py：实际消息发送逻辑
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from nonebot import logger

if TYPE_CHECKING:
    from .moonlark_main import MoonlarkMain


class ProactiveChatController:
    """EGO 内部的主动私聊决策控制器"""

    def __init__(self, moonlark_main: "MoonlarkMain") -> None:
        self.moonlark_main = moonlark_main
        # {user_id: {"timestamp": datetime, "topic": str, "replied": bool}}
        self.last_private_chats: dict[str, dict] = {}
        self.cooldown_seconds: int = 1800  # 30 分钟
        self.pending_queue: list[dict] = []  # 待发送的私聊任务

    async def send_private_message(
        self, target: str, reason: str, content_hint: str
    ) -> bool:
        """决策并发送主动私聊消息

        Args:
            target: 目标用户ID
            reason: 私聊理由
            content_hint: 聊什么的提示

        Returns:
            是否成功发送
        """
        # 1. 检查冷却
        if self._in_cooldown(target):
            logger.info(f"[ProactiveChatCtrl] 用户 {target} 在冷却期内，跳过")
            return False

        # 2. 调用实际发送模块
        try:
            from ..proactive_chat import send_proactive_private_message
            from nonebot import get_bot
            from ...models import PrivateChatSession
            from nonebot_plugin_orm import get_session
            from sqlalchemy import select

            # 获取 bot 和 user_id
            async with get_session() as db_session:
                result = await db_session.execute(
                    select(PrivateChatSession).where(PrivateChatSession.user_id == target)
                )
                chat_session = result.scalar_one_or_none()

            if not chat_session:
                logger.warning(f"[ProactiveChatCtrl] 用户 {target} 无私聊会话记录")
                return False

            bot = get_bot(chat_session.bot_id)
            await send_proactive_private_message(bot, target, content_hint)

            # 3. 更新记录
            self.last_private_chats[target] = {
                "timestamp": datetime.now(),
                "topic": content_hint,
                "replied": False,
            }
            logger.info(f"[ProactiveChatCtrl] 已向 {target} 发送主动私聊: {content_hint}")
            return True

        except Exception as e:
            logger.exception(f"[ProactiveChatCtrl] 发送失败: {e}")
            return False

    def update_reply_status(self, user_id: str, replied: bool = True) -> None:
        """当用户回复了主动私聊时回调"""
        if user_id in self.last_private_chats:
            self.last_private_chats[user_id]["replied"] = replied

    def get_cooldown_info(self) -> dict:
        """返回所有用户的冷却状态，供 MoonlarkMain 使用"""
        return {
            user_id: {
                "last_chat": info["timestamp"],
                "in_cooldown": self._in_cooldown(user_id),
                "replied": info["replied"],
                "topic": info["topic"],
            }
            for user_id, info in self.last_private_chats.items()
        }

    def _in_cooldown(self, user_id: str) -> bool:
        """检查用户是否在冷却期"""
        if user_id not in self.last_private_chats:
            return False
        last_time = self.last_private_chats[user_id]["timestamp"]
        return (datetime.now() - last_time).total_seconds() < self.cooldown_seconds

    def get_last_private_info(self, user_id: str) -> Optional[dict]:
        """获取上次私聊信息"""
        return self.last_private_chats.get(user_id)
