from datetime import datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class TurtleSoupGame(Model):
    """进行中的一局海龟汤（一个会话最多一条）。

    谜题与问答历史以 JSON 文本保存：谜题包含 ``supplementary_info`` 数组，
    历史是 ``HistoryItem`` 的数组，结构简单且只被本插件读取。
    """

    __tablename__ = "nonebot_plugin_turtle_soup_game"

    id_: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(String(128))
    puzzle_data: Mapped[str] = mapped_column(Text)
    history_data: Mapped[str] = mapped_column(Text, default="[]")
    percent: Mapped[int] = mapped_column(Integer, default=0)
    asked: Mapped[int] = mapped_column(Integer, default=0)
    hint_index: Mapped[int] = mapped_column(Integer, default=0)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    expire_time: Mapped[datetime] = mapped_column(DateTime, index=True)


class TurtleSoupPlayer(Model):
    """玩家统计：正确作答数（排行榜数据来源）。"""

    __tablename__ = "nonebot_plugin_turtle_soup_player"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    last_correct_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
