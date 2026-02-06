from datetime import datetime
from typing import Optional, TypedDict

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import LargeBinary, String, Text, Float, Integer
from sqlalchemy.dialects.mysql import MEDIUMBLOB

# 创建跨数据库兼容的二进制类型：MySQL 使用 MEDIUMBLOB (16MB)，其他数据库使用 LargeBinary
CompatibleBlob = LargeBinary().with_variant(MEDIUMBLOB(), "mysql")


class ChatGroup(Model):
    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    blocked_user: Mapped[str] = mapped_column(Text(), default="[]")
    enabled: Mapped[bool]


class Note(Model):
    """Note model for storing user-generated notes with optional expiration and keywords"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    context_id: Mapped[str] = mapped_column(String(128), index=True)  # user_id for private, group_id for groups
    content: Mapped[str] = mapped_column(Text())
    keywords: Mapped[str] = mapped_column(String(length=256), default="")
    created_time: Mapped[float] = mapped_column(Float())
    expire_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # Optional expiration time

class RuaData(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    action_id: Mapped[int]
    count: Mapped[int] = mapped_column(default=0)


class UserProfile(Model):
    """User profile model for storing user-defined profiles that appear in chat context"""

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_content: Mapped[str] = mapped_column(Text())


class Sticker(Model):
    """Sticker model for storing saved stickers/memes"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    description: Mapped[str] = mapped_column(Text())  # VLM 生成的视觉描述
    # MySQL 使用 MEDIUMBLOB (16MB)，SQLite 使用 LargeBinary（无大小限制）
    raw: Mapped[bytes] = mapped_column(CompatibleBlob)  # 二进制图片数据
    group_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)  # 来源群聊
    created_time: Mapped[float] = mapped_column(Float())  # 创建时间戳
    p_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 感知哈希，用于图片查重
    # 表情包分类索引信息（LLM 生成）
    meme_text: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)  # 表情包中的文本
    emotion: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 表情包表达的情绪
    labels: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)  # 表情包标签（JSON 数组）
    context_keywords: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)  # 适用语境关键词（JSON 数组）


class MessageQueueCache(Model):
    """消息队列缓存，用于持久化 OpenAI 消息历史以便重启后恢复"""

    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)  # 群组 ID，主键确保每个群组只有一条记录
    messages_json: Mapped[str] = mapped_column(Text())  # JSON 序列化的消息列表
    consecutive_bot_messages: Mapped[int] = mapped_column(Integer(), default=0)  # 连续 bot 消息计数
    updated_time: Mapped[float] = mapped_column(Float())  # 最后更新时间戳


class RuaAction(TypedDict):
    name: str
    refusable: bool
    unlock_favorability: float
