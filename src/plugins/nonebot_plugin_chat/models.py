from datetime import datetime
from typing import Literal, Optional, Union
from typing_extensions import TypedDict

from nonebot_plugin_orm import Model
from pydantic import BaseModel, Field
from sqlalchemy import BINARY, DateTime, Float, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.mysql import MEDIUMBLOB, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

# 创建跨数据库兼容的二进制类型：MySQL 使用 MEDIUMBLOB (16MB)，其他数据库使用 LargeBinary
CompatibleBlob = LargeBinary().with_variant(MEDIUMBLOB(), "mysql")

# 创建跨数据库兼容的大文本类型：MySQL 使用 MEDIUMTEXT (16MB)，其他数据库使用 Text
CompatibleMediumText = Text().with_variant(MEDIUMTEXT(), "mysql")


class ChatGroup(Model):
    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    blocked_user: Mapped[str] = mapped_column(Text(), default="[]")
    blocked_keyword: Mapped[str] = mapped_column(Text(), default="[]")
    ignore_mention_user: Mapped[str] = mapped_column(Text(), default="[]")
    enabled: Mapped[bool]
    dropping_enabled: Mapped[bool] = mapped_column(default=True)


class ActionDecisionResponse(BaseModel):
    approved: bool
    allocated_time: int


class SleepDecisionResponse(BaseModel):
    approved: bool


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

    message_id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(128))
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 上下文 trace ID，用于重启后恢复
    # MySQL 使用 MEDIUMTEXT (16MB)，SQLite 使用 Text（无大小限制）
    message_json: Mapped[str] = mapped_column(CompatibleMediumText)  # JSON 序列化的消息列表
    updated_time: Mapped[datetime] = mapped_column(DateTime(), default=datetime.now)  # 最后更新时间戳
    message_hash: Mapped[bytes] = mapped_column(
        BINARY(32).with_variant(LargeBinary(32), "sqlite"),
    )  # 消息哈希，用于去重


class JudgeData(BaseModel):
    target: str
    score: Literal[-2, -1, 0, 1, 2]
    reason: str


class ModelResponse(BaseModel, extra="forbid"):
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
    session_key: Mapped[str] = mapped_column(String(256))  # 带 platform 前缀的 session key（如 qq_USERID）
    bot_id: Mapped[str] = mapped_column(String(128))  # 用户最后使用的 bot ID
    last_message_time: Mapped[float] = mapped_column(Float())  # 最后消息时间戳
    last_proactive_message_time: Mapped[Optional[float]] = mapped_column(Float(), nullable=True)  # 最后主动消息时间戳


class InstantMemoryCache(Model):
    """即时记忆持久化缓存"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)  # 会话 ID
    content: Mapped[str] = mapped_column(Text())  # 记忆内容
    name: Mapped[str] = mapped_column(String(128), default="")  # 记忆名称
    created_time: Mapped[datetime] = mapped_column(DateTime(), default=datetime.now)  # 创建时间
    expire_time: Mapped[datetime] = mapped_column(DateTime())  # 过期时间


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


# ========================================================================
# EGO 决策相关模型
# ========================================================================


class PrivateChatDecision(BaseModel):
    """主动私聊决策"""

    target: str
    reason: str
    content_hint: str


class EgoDecisionResponse(BaseModel):
    """MoonlarkMain request_think 的 LLM 返回格式"""

    sleep_decision: Optional[Literal["go_to_sleep", "wake_up"]] = None
    blog_action: Optional[Union[str, dict]] = (
        None  # "skip" | "continue_draft" | "abort_draft" | {"start_new_topic": "主题"}
    )
    private_chat: Optional[PrivateChatDecision] = None
    self_action: Optional[str] = None  # 活动描述，不返回即不动作


class SleepThinkResponse(BaseModel):
    """SleepController request_think 的 LLM 返回格式"""
    wake_up: bool = False
    reason: str = ""


class SelfActionDurationResponse(BaseModel):
    """SelfActionController _generate_duration 的 LLM 返回格式"""

    duration_minutes: int = 5


class TaskClassificationResponse(BaseModel):
    """TaskController _classify_task 的 LLM 返回格式"""

    activity_type: Literal["学习", "任务", "消息"]


class SelfActionResultProcessResponse(BaseModel):
    """SelfActionController 结果处理的 LLM 返回格式"""

    compressed_content: str
    keywords: str
    expire_hours: float = 168


class AgentEvent(Model):
    """智能体事件记录表，记录思考、动作、动作结果及外部事件"""

    __tablename__ = "nonebot_plugin_chat_diaryentry"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), index=True)
    content: Mapped[str] = mapped_column(Text())


class DiaryPost(Model):
    """生成的日记存储表，由每日凌晨任务自动生成"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text())
    keywords: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), index=True)
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)


class DiaryProcessResponse(BaseModel):
    """日记处理 LLM 返回格式（关键词 + 过期时间）"""

    keywords: str = Field(description="关键词，空格分隔，至少 1 个")
    expire_hours: float = Field(description="根据信息时效性估算的过期时间（小时），禁止 -1（永不过期）", gt=0)


class Timer(Model):
    """LLM 定时器持久化存储，确保重启后可恢复"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    trigger_time: Mapped[datetime] = mapped_column(DateTime(), index=True)
    description: Mapped[str] = mapped_column(Text())
