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
        # {nickname: {"timestamp": datetime, "topic": str, "replied": bool,
        #              "unreplied_count": int, "today_count": int, "today_date": str}}
        self.last_private_chats: dict[str, dict] = {}
        self.cooldown_seconds: int = 1800  # 30 分钟
        self.pending_queue: list[dict] = []  # 待发送的私聊任务

    async def send_private_message(
        self, target: str, reason: str, content_hint: str
    ) -> bool:
        """决策并发送主动私聊消息

        Args:
            target: 目标用户昵称
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
            from nonebot_plugin_larkuser.utils.user import get_user
            from sqlalchemy import select

            # 按昵称匹配用户
            async with get_session() as db_session:
                all_sessions = (await db_session.execute(select(PrivateChatSession))).scalars().all()

            matched_user_id = None
            matched_bot_id = None
            for chat_session in all_sessions:
                user = await get_user(chat_session.user_id)
                if user.get_nickname() == target:
                    matched_user_id = chat_session.user_id
                    matched_bot_id = chat_session.bot_id
                    break

            if not matched_user_id:
                logger.warning(f"[ProactiveChatCtrl] 未找到昵称为 {target} 的好友会话")
                return False

            bot = get_bot(matched_bot_id)
            await send_proactive_private_message(bot, matched_user_id, content_hint)

            # 3. 更新记录（用昵称作为 key）
            today = datetime.now().strftime("%Y-%m-%d")
            existing = self.last_private_chats.get(target, {})
            # 如果之前的私聊未回复，累加未回复计数
            prev_unreplied = 0
            if existing and not existing.get("replied", True):
                prev_unreplied = existing.get("unreplied_count", 0)
            # 每日计数：跨日重置
            today_count = existing.get("today_count", 0) if existing.get("today_date") == today else 0

            self.last_private_chats[target] = {
                "timestamp": datetime.now(),
                "topic": content_hint,
                "replied": False,
                "unreplied_count": prev_unreplied + 1,
                "today_count": today_count + 1,
                "today_date": today,
            }
            logger.info(f"[ProactiveChatCtrl] 已向 {target} 发送主动私聊: {content_hint}")
            return True

        except Exception as e:
            logger.exception(f"[ProactiveChatCtrl] 发送失败: {e}")
            return False

    async def update_reply_status(self, user_id: str, replied: bool = True) -> None:
        """当用户回复了主动私聊时回调（user_id → 解析昵称 → 重置未回复计数）"""
        try:
            from nonebot_plugin_larkuser.utils.user import get_user
            user = await get_user(user_id)
            nickname = user.get_nickname()

            if nickname in self.last_private_chats:
                if replied:
                    self.last_private_chats[nickname]["replied"] = True
                    self.last_private_chats[nickname]["unreplied_count"] = 0
                    logger.info(f"[ProactiveChatCtrl] 用户 {nickname} 已回复，重置未回复计数")
        except Exception as e:
            logger.exception(f"[ProactiveChatCtrl] update_reply_status 失败: {e}")

    def get_cooldown_info(self) -> dict:
        """返回所有用户的冷却状态，供 MoonlarkMain 使用"""
        today = datetime.now().strftime("%Y-%m-%d")
        result = {}
        for user_id, info in self.last_private_chats.items():
            # 跨日重置每日计数
            today_count = info.get("today_count", 0) if info.get("today_date") == today else 0
            result[user_id] = {
                "last_chat": info["timestamp"],
                "in_cooldown": self._in_cooldown(user_id),
                "replied": info["replied"],
                "topic": info["topic"],
                "unreplied_count": info.get("unreplied_count", 0),
                "today_count": today_count,
            }
        return result

    def _in_cooldown(self, user_id: str) -> bool:
        """检查用户是否在冷却期"""
        if user_id not in self.last_private_chats:
            return False
        last_time = self.last_private_chats[user_id]["timestamp"]
        return (datetime.now() - last_time).total_seconds() < self.cooldown_seconds

    def get_last_private_info(self, user_id: str) -> Optional[dict]:
        """获取上次私聊信息"""
        return self.last_private_chats.get(user_id)
