from datetime import datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Integer, DateTime, JSON


class CommandUsage(Model):
    command_name: Mapped[str] = mapped_column(String(256), primary_key=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)


class HandlerResultRecord(Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command_name: Mapped[str] = mapped_column(String(256))
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    matcher: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ExceptionRecord(Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exception: Mapped[str] = mapped_column(Text)
    session: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bot_id: Mapped[str] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class OpenAIHistoryRecord(Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(128))
    identify: Mapped[str] = mapped_column(String(256))
    messages: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
