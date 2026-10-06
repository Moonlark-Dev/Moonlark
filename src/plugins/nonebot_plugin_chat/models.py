from datetime import datetime
from typing import Literal, Optional, Union
from typing_extensions import TypedDict

from nonebot_plugin_orm import Model
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, Integer, LargeBinary, String, Text, false, func
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
    interaction_mode: Mapped[str] = mapped_column(String(16), default="standard")
    # 主人是否在本群的 Message Summary 记录中出现过；一旦为 True 不再自动改回 False
    master_present: Mapped[bool] = mapped_column(default=False, server_default=false())


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


class ChatContextMessage(Model):
    """Chat Context 消息表：一条记录即对话上下文中的一条消息

    由 ``core/context.py`` 的 :class:`~nonebot_plugin_chat.core.context.ChatContext`
    负责读写。``(session_id, context_index, index)`` 为复合主键：

    - ``context_index``：上下文序号，同一会话内只增不减，最大的一条即最新会话；
    - ``index``：同一 ``context_index`` 内递增的消息序号；
    - ``block_id``：事件总结的 block 标记（不属于主键）。0 表示 system / meta 前导消息，
      真实 block 从 1 开始；同一 block 的消息会被一起提交给事件总结，
      收集完成后下一个 block 才启用新的 block_id。
    """

    __tablename__ = "nonebot_plugin_chat_contextmessage"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    context_index: Mapped[int] = mapped_column(Integer(), primary_key=True)
    index: Mapped[int] = mapped_column(Integer(), primary_key=True)
    block_id: Mapped[int] = mapped_column(Integer(), default=0, index=True)
    role: Mapped[str] = mapped_column(String(16))  # assistant / system / user / tool
    sub_type: Mapped[str] = mapped_column(String(16), default="")  # user 消息为 event / message / meta，其余为空
    timestamp: Mapped[datetime] = mapped_column(DateTime(), default=datetime.now)  # 消息创建时间
    # 传给 OpenAI SDK 的 content，JSON 序列化（字符串或多模态 part 列表）
    content: Mapped[str] = mapped_column(CompatibleMediumText)
    # processor 解析出来的 json（用户消息为 CachedMessage），其余留空
    data: Mapped[Optional[str]] = mapped_column(CompatibleMediumText, nullable=True)
    # assistant 消息的工具调用列表，JSON 序列化；tool 消息的 tool_call_id
    tool_calls: Mapped[Optional[str]] = mapped_column(CompatibleMediumText, nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(16), default="none")  # 非 user 消息恒为 none
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)


class PreTriggerSignals(BaseModel):
    """回复触发前的预处理信号，由 Jev 依据最近的聊天记录判定（见 utils/jev_judge.py）"""

    truncate: bool
    help_needed: bool
    emotional_support_needed: bool
    chatting_alone: bool
    tech_topic: bool


class PrivateChatConfig(Model):
    """记录用户私聊 Chat 功能的开关状态，默认开启"""

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)


class PrivateChatSession(Model):
    """记录用户私聊会话信息，用于主动消息时获取正确的 bot"""

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_key: Mapped[str] = mapped_column(String(256))  # 带 platform 前缀的 session key（如 qq_USERID）
    bot_id: Mapped[str] = mapped_column(String(128))  # 用户最后使用的 bot ID
    adapter_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 私聊适配器名，历史记录为空
    platform_user_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )  # 适配器原始 user_id（如 openid）
    last_message_time: Mapped[float] = mapped_column(Float())  # 最后消息时间戳
    last_proactive_message_time: Mapped[Optional[float]] = mapped_column(Float(), nullable=True)  # 最后主动消息时间戳
    unreplied_count: Mapped[int] = mapped_column(
        Integer(), default=0
    )  # 连续未回复主动私聊次数（用户任意私聊消息时重置）


class ProactiveChatRecord(Model):
    """主动私聊发送记录，供主动私聊决策（Decide）参考最近若干次发送情况"""

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    nickname: Mapped[str] = mapped_column(String(128), default="")  # 发送时的用户昵称
    content: Mapped[str] = mapped_column(Text())  # 实际发送的主动私聊内容
    sent_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.now, index=True)


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


class SessionEvent(Model):
    """按会话收集的事件和话题记录，每个 block（默认 50 条消息）收集一次"""

    __tablename__ = "nonebot_plugin_chat_sessionevent"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    date: Mapped[str] = mapped_column(String(16), index=True)  # YYYY-MM-DD
    content: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(), default=datetime.now)
    # 该事件总结对应的 ChatContextMessage.block_id，滑动窗口按 block 回溯删除历史消息
    block_id: Mapped[int] = mapped_column(Integer(), default=0, server_default="0", index=True)
