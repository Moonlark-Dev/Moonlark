from datetime import datetime
from typing import Any, Literal, Optional, TypedDict, Union

from nonebot_plugin_orm import Model
from pydantic import BaseModel, Field
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON, DateTime, LargeBinary, String, Text, Float, Integer
from sqlalchemy.dialects.mysql import MEDIUMBLOB, MEDIUMTEXT

# 创建跨数据库兼容的二进制类型：MySQL 使用 MEDIUMBLOB (16MB)，其他数据库使用 LargeBinary
CompatibleBlob = LargeBinary().with_variant(MEDIUMBLOB(), "mysql")

# 创建跨数据库兼容的大文本类型：MySQL 使用 MEDIUMTEXT (16MB)，其他数据库使用 Text
CompatibleMediumText = Text().with_variant(MEDIUMTEXT(), "mysql")


class ChatGroup(Model):
    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    blocked_user: Mapped[str] = mapped_column(Text(), default="[]")
    blocked_keyword: Mapped[str] = mapped_column(Text(), default="[]")
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
    # MySQL 使用 MEDIUMTEXT (16MB)，SQLite 使用 Text（无大小限制）
    messages_json: Mapped[str] = mapped_column(CompatibleMediumText)  # JSON 序列化的消息列表
    updated_time: Mapped[float] = mapped_column(Float())  # 最后更新时间戳


class JudgeData(BaseModel):
    target: str
    score: Literal[-2, -1, 0, 1, 2]
    reason: str


class ModelResponse(BaseModel, extra='forbid'):
    reply_required: bool
    mood: Optional[
        Literal[
            "joy",
            "sadness",
            "anger",
            "fear",
            "surprise",
            "disgust",
            "trust",
            "anticipation",
            "calm",
            "bored",
            "confused",
            "tired",
            "shy",
        ]
    ]
    mood_intensity: float = Field(0.8, ge=0.5, le=1.2)
    mood_reason: Optional[str] = None
    favorability_judge: Optional[JudgeData] = None
    interest: Optional[float] = Field(None, ge=0.0, le=1.0)
    thought: Optional[str] = None


class PrivateChatSession(Model):
    """记录用户私聊会话信息，用于主动消息时获取正确的 bot"""

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(128))  # 用户最后使用的 bot ID
    last_message_time: Mapped[float] = mapped_column(Float())  # 最后消息时间戳
    last_proactive_message_time: Mapped[Optional[float]] = mapped_column(Float(), nullable=True)  # 最后主动消息时间戳


class MainSessionActionHistory(Model):
    """MainSession 数据持久化存储，用于保存 action_history"""
    id_: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    start_time: Mapped[datetime] = mapped_column(DateTime())
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)
    action: Mapped[dict[str, Any]] = mapped_column(JSON())


class BlogPost(Model):
    """Blog post model for storing Moonlark's blog posts"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text())
    create_at: Mapped[datetime] = mapped_column(default=datetime.now)


class SkipAction(BaseModel):
    type: Literal["skip"]


class CustomAction(BaseModel):
    type: Literal["do"]
    information: str
    estimated_time: int


class SendPrivateMsgAction(BaseModel):
    type: Literal["send_private_message"]
    target_nickname: str
    subject: str


class RestAction(BaseModel):
    type: Literal["sleep"]
    time: int


class FetchChatHistoryAction(BaseModel):
    type: Literal["fetch_chat_history"]
    context_id: str


class WriteBlogAction(BaseModel):
    type: Literal["write_blog"]
    title: str
    content: str


BoredAction = Union[SkipAction, CustomAction, SendPrivateMsgAction, RestAction, FetchChatHistoryAction, WriteBlogAction]


class BoredActionResponse(BaseModel):
    response: BoredAction


# Action 状态类型
class ActionState(TypedDict, total=False):
    """动作执行后的状态信息"""

    # sleep 动作的状态
    actual_sleep_minutes: Optional[int]  # 实际睡眠时间（分钟）
    sleep_interrupted: Optional[bool]  # 是否被提前唤醒

    # send_private_message 动作的状态
    user_replied: Optional[bool]  # 用户是否回复
    reply_time: Optional[datetime]  # 用户回复时间
