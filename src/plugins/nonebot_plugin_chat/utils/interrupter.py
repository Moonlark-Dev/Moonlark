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

import random
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List, Dict

if TYPE_CHECKING:
    from ..matcher.group import GroupSession
from nonebot.log import logger

# 预编译正则表达式以提高性能
KEYWORD_REGEX = re.compile(r"[\w\u4e00-\u9fff]+")


class FrequencyCounter:
    def __init__(self):
        self.short_term_responses: List[datetime] = []  # 短期响应时间记录
        self.long_term_messages: List[datetime] = []  # 长期消息时间记录

    def add_response(self):
        """记录一次机器人响应"""
        now = datetime.now()
        self.short_term_responses.append(now)
        self._cleanup_old_records()

    def get_short_term_response_count(self, seconds: int = 30) -> int:
        """获取短期响应次数"""
        cutoff_time = datetime.now() - timedelta(seconds=seconds)
        return len([t for t in self.short_term_responses if t > cutoff_time])

    def get_long_term_message_rate(self, seconds: int = 60) -> int:
        """获取长期消息频率"""
        cutoff_time = datetime.now() - timedelta(seconds=seconds)
        return len([t for t in self.long_term_messages if t > cutoff_time])

    def add_message(self):
        """记录一条群消息"""
        now = datetime.now()
        self.long_term_messages.append(now)
        self._cleanup_old_records()

    def _cleanup_old_records(self):
        """清理过期记录"""
        cutoff_time = datetime.now() - timedelta(minutes=5)
        self.short_term_responses = [t for t in self.short_term_responses if t > cutoff_time]
        self.long_term_messages = [t for t in self.long_term_messages if t > cutoff_time]


class UserBehaviorTracker:
    def __init__(self):
        self.active_users: Dict[str, List[datetime]] = {}  # 活跃用户记录

    def record_user_interaction(self, user_id: str):
        """记录用户与机器人的互动"""
        if user_id not in self.active_users:
            self.active_users[user_id] = []
        self.active_users[user_id].append(datetime.now())
        self._cleanup_old_records()

    def is_active_user(self, user_id: str) -> bool:
        """检查是否为活跃用户"""
        if user_id not in self.active_users:
            return False
        cutoff_time = datetime.now() - timedelta(days=1)
        recent_interactions = [t for t in self.active_users[user_id] if t > cutoff_time]
        return len(recent_interactions) >= 3  # 过去一天内至少互动3次

    def is_new_user(self, user_id: str) -> bool:
        """检查是否为新用户"""
        if user_id not in self.active_users:
            return True
        cutoff_time = datetime.now() - timedelta(hours=1)
        recent_interactions = [t for t in self.active_users[user_id] if t > cutoff_time]
        return len(recent_interactions) == 0

    def _cleanup_old_records(self):
        """清理过期记录"""
        cutoff_time = datetime.now() - timedelta(days=2)
        for user_id in list(self.active_users.keys()):
            self.active_users[user_id] = [t for t in self.active_users[user_id] if t > cutoff_time]
            if not self.active_users[user_id]:
                del self.active_users[user_id]


class Interrupter:
    def __init__(self, group_session: "GroupSession"):
        self.group_session = group_session
        self.cooldown_end_time = datetime.min  # 冷却结束时间
        self.sleep_end_time = datetime.min  # 休眠结束时间
        self.last_active_time = datetime.now()  # 上次活跃时间
        self.frequency_counter = FrequencyCounter()
        self.user_behavior_tracker = UserBehaviorTracker()
        self.block_keywords = ["闭嘴", "别说话", "安静", "歇会"]  # 阻止关键词列表
        self.required_emojis = ["🐶", "😂"]  # 必须响应的表情符号

    async def should_interrupt(self, message: str, user_id: str) -> bool:
        """
        检查是否应该阻断机器人响应
        返回 True 表示应该阻断，False 表示不应该阻断
        """
        logger.debug(f"Checking interrupt conditions for message: {message}")

        # 1. 首先检查频率阻断
        if self._check_frequency_interrupt():
            logger.debug("Interrupted by frequency check")
            return True

        # 2. 然后检查关键词阻断
        if self._check_keyword_interrupt(message):
            logger.debug("Interrupted by keyword check")
            return True

        # 3. 接着检查时间相关阻断
        if self._check_time_related_interrupt():
            logger.debug("Interrupted by time-related check")
            return True

        # 4. 检查游戏化阻断
        if self._check_gamification_interrupt(message):
            logger.debug("Interrupted by gamification check")
            return True

        # 5. 最后应用基础随机阻断和用户行为阻断
        if self._check_random_interrupt(user_id):
            logger.debug("Interrupted by random check")
            return True

        # 更新活跃时间
        self.update_last_active_time()

        logger.debug("No interrupt conditions met, proceeding with response")
        return False

    def _check_random_interrupt(self, user_id: str) -> bool:
        """基础随机阻断（概率性沉默）"""
        # 活跃用户降低阻断概率
        if self.user_behavior_tracker.is_active_user(user_id):
            interrupt_probability = 0.1  # 10%概率阻断
            logger.debug(f"Active user {user_id}, using {interrupt_probability*100}% interrupt probability")
        else:
            interrupt_probability = 0.2  # 20%概率阻断
            logger.debug(f"Non-active user {user_id}, using {interrupt_probability*100}% interrupt probability")

        should_interrupt = random.random() < interrupt_probability
        logger.debug(
            f"Random interrupt check for user {user_id}: {'Interrupted' if should_interrupt else 'Not interrupted'}"
        )
        return should_interrupt

    def _check_keyword_interrupt(self, message: str) -> bool:
        """关键词阻断（主动沉默）"""
        # 检查是否包含阻止关键词
        for keyword in self.block_keywords:
            if keyword in message:
                logger.debug(f"Message blocked by keyword: {keyword}")
                return True

        # 检查是否为重复内容（最近5条消息内有重复关键词）
        if self._check_duplicate_content(message):
            logger.debug("Message blocked by duplicate content")
            return True

        logger.debug("Message passed keyword check")
        return False

    def _check_duplicate_content(self, message: str) -> bool:
        """检查是否为重复内容"""
        # 获取最近5条消息
        recent_messages = self.group_session.cached_messages[-5:] if self.group_session.cached_messages else []

        # 提取消息中的关键词（简单实现，可以进一步优化）
        message_keywords = set(KEYWORD_REGEX.findall(message))

        # 检查最近消息中是否有相似关键词
        for cached_msg in recent_messages:
            if cached_msg["self"]:  # 只检查机器人发送的消息
                cached_keywords = set(KEYWORD_REGEX.findall(cached_msg["content"]))
                # 如果有超过50%的关键词重叠，认为是重复内容
                if (
                    len(cached_keywords) > 0
                    and len(message_keywords.intersection(cached_keywords)) / len(cached_keywords) > 0.5
                ):
                    return True

        return False

    def _check_frequency_interrupt(self) -> bool:
        """频率阻断（防刷屏）"""
        # 检查是否处于冷却状态
        if datetime.now() < self.cooldown_end_time:
            logger.debug("Message blocked by cooldown period")
            return True

        # 检查短期频率（30秒内3条消息）
        short_term_count = self.frequency_counter.get_short_term_response_count(30)
        if short_term_count >= 3:
            self.cooldown_end_time = datetime.now() + timedelta(seconds=15)
            logger.debug(f"Message blocked by short-term frequency limit ({short_term_count} responses in 30 seconds)")
            return True

        # 检查长期频率（1分钟内20条消息）
        long_term_count = self.frequency_counter.get_long_term_message_rate(60)
        if long_term_count > 20:
            # 降低响应概率至10%
            should_respond = random.random() < 0.1
            logger.debug(
                f"Long-term frequency limit exceeded ({long_term_count} messages in 60 seconds), responding with 10% probability: {'Yes' if should_respond else 'No'}"
            )
            return not should_respond

        logger.debug("Message passed frequency check")
        return False

    def _check_time_related_interrupt(self) -> bool:
        """时间相关阻断（活跃时段优化）"""
        now = datetime.now()
        current_hour = now.hour

        # 低活跃时段（凌晨2点到6点）
        if 2 <= current_hour < 6:
            should_interrupt = random.random() < 0.5  # 50%概率阻断
            logger.debug(
                f"Low activity period (hour {current_hour}), interrupting with 50% probability: {'Yes' if should_interrupt else 'No'}"
            )
            return should_interrupt

        # 检查是否为冷场后第一条消息（连续5分钟无消息）
        time_since_last_active = now - self.last_active_time
        if time_since_last_active > timedelta(minutes=5):
            # 冷场后的第一条消息总是响应，不阻断
            logger.debug("First message after cold period, always responding")
            return False

        # 高活跃时段（晚上7点到10点）正常响应
        if 19 <= current_hour < 22:
            logger.debug(f"High activity period (hour {current_hour}), normal response")
            return False

        logger.debug(f"Normal period (hour {current_hour}), normal response")
        return False  # 其他时段正常处理

    def _check_gamification_interrupt(self, message: str) -> bool:
        """游戏化阻断（趣味挑战）"""
        # 检查是否处于休眠模式
        if datetime.now() < self.sleep_end_time:
            logger.debug("Message blocked by sleep mode")
            return True

        # 隐藏任务：包含特定表情符号必须响应
        for emoji in self.required_emojis:
            if emoji in message:
                logger.debug(f"Message contains required emoji {emoji}, always responding")
                return False  # 不阻断

        # 随机进入休眠模式（0.5%概率）
        if random.random() < 0.005:
            self.sleep_end_time = datetime.now() + timedelta(minutes=1)
            logger.debug("Entering sleep mode for 1 minute")
            # 发送提示消息"我去喝杯茶，一会回来！"
            # 这个消息发送需要在调用处处理
            return True

        logger.debug("Message passed gamification check")
        return False

    def update_last_active_time(self):
        """更新上次活跃时间"""
        self.last_active_time = datetime.now()

    def record_response(self):
        """记录一次机器人响应"""
        logger.debug("Recording robot response")
        self.frequency_counter.add_response()

    def record_message(self):
        """记录一条群消息"""
        logger.debug("Recording group message")
        self.frequency_counter.add_message()

    def record_user_interaction(self, user_id: str):
        """记录用户与机器人的互动"""
        logger.debug(f"Recording user interaction for user {user_id}")
        self.user_behavior_tracker.record_user_interaction(user_id)
