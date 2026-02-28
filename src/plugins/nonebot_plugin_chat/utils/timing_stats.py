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

from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from nonebot.log import logger


@dataclass
class SessionTimingStats:
    """单个会话的时间统计数据"""

    # 抓取用时统计
    total_fetch_time_ms: float = 0.0
    fetch_count: int = 0

    # 回应用时统计
    total_reply_time_ms: float = 0.0
    reply_count: int = 0

    # 抓取开始时间（用于计算抓取用时）
    fetch_start_time: Optional[datetime] = None

    def record_fetch_time(self, time_ms: float) -> None:
        """记录一次抓取用时"""
        self.total_fetch_time_ms += time_ms
        self.fetch_count += 1
        logger.debug(f"[TimingStats] Fetch time recorded: {time_ms:.2f}ms, count: {self.fetch_count}")

    def record_reply_time(self, time_ms: float) -> None:
        """记录一次回应用时"""
        self.total_reply_time_ms += time_ms
        self.reply_count += 1
        logger.debug(f"[TimingStats] Reply time recorded: {time_ms:.2f}ms, count: {self.reply_count}")

    def start_fetch(self) -> None:
        """开始抓取计时"""
        self.fetch_start_time = datetime.now()

    def end_fetch(self) -> Optional[float]:
        """结束抓取计时，返回用时（毫秒），如果未开始则返回None"""
        if self.fetch_start_time is None:
            return None
        elapsed_ms = (datetime.now() - self.fetch_start_time).total_seconds() * 1000
        self.fetch_start_time = None
        return elapsed_ms

    @property
    def avg_fetch_time_ms(self) -> Optional[float]:
        """平均抓取用时（毫秒）"""
        if self.fetch_count == 0:
            return None
        return self.total_fetch_time_ms / self.fetch_count

    @property
    def avg_reply_time_ms(self) -> Optional[float]:
        """平均回应用时（毫秒）"""
        if self.reply_count == 0:
            return None
        return self.total_reply_time_ms / self.reply_count

    def reset(self) -> None:
        """重置统计数据"""
        self.total_fetch_time_ms = 0.0
        self.fetch_count = 0
        self.total_reply_time_ms = 0.0
        self.reply_count = 0
        self.fetch_start_time = None


class TimingStatsManager:
    """时间统计管理器 - 单例模式"""

    _instance: Optional["TimingStatsManager"] = None
    _initialized: bool = False

    def __new__(cls) -> "TimingStatsManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if TimingStatsManager._initialized:
            return

        # 存储所有会话的统计数据
        # key: session_id, value: SessionTimingStats
        self._stats: dict[str, SessionTimingStats] = {}

        # 全局统计（所有会话合计）
        self._global_stats = SessionTimingStats()

        TimingStatsManager._initialized = True

    def _get_session_stats(self, session_id: str) -> SessionTimingStats:
        """获取或创建会话的统计数据"""
        if session_id not in self._stats:
            self._stats[session_id] = SessionTimingStats()
        return self._stats[session_id]

    def record_fetch_start(self, session_id: str) -> None:
        """记录抓取开始时间"""
        stats = self._get_session_stats(session_id)
        stats.start_fetch()

    def record_fetch_end(self, session_id: str) -> None:
        """记录抓取结束并计算用时"""
        stats = self._get_session_stats(session_id)
        elapsed_ms = stats.end_fetch()

        if elapsed_ms is None:
            logger.warning(f"[TimingStats] No fetch start time found for session {session_id}")
            return

        stats.record_fetch_time(elapsed_ms)
        self._global_stats.record_fetch_time(elapsed_ms)

        logger.info(f"[TimingStats] Session {session_id}: fetch_reply took {elapsed_ms:.2f}ms")

    def record_reply_time(self, session_id: str, reply_time_ms: float) -> None:
        """记录回应用时（直接使用传入的时间差）"""
        stats = self._get_session_stats(session_id)
        stats.record_reply_time(reply_time_ms)
        self._global_stats.record_reply_time(reply_time_ms)

        logger.info(f"[TimingStats] Session {session_id}: reply took {reply_time_ms:.2f}ms")

    def get_session_stats(self, session_id: str) -> Optional[SessionTimingStats]:
        """获取指定会话的统计数据"""
        return self._stats.get(session_id)

    def get_global_stats(self) -> SessionTimingStats:
        """获取全局统计数据"""
        return self._global_stats

    def get_all_session_ids(self) -> list[str]:
        """获取所有会话ID列表"""
        return list(self._stats.keys())

    def reset_session_stats(self, session_id: str) -> bool:
        """重置指定会话的统计数据"""
        if session_id in self._stats:
            self._stats[session_id].reset()
            return True
        return False

    def reset_global_stats(self) -> None:
        """重置全局统计数据"""
        self._global_stats.reset()

    def reset_all_stats(self) -> None:
        """重置所有统计数据"""
        self._stats.clear()
        self._global_stats.reset()


# 全局单例实例
timing_stats_manager = TimingStatsManager()
