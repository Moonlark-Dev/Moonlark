from datetime import datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class BroadcastGroup(Model):
    """bc 自己维护的群列表

    这张表在收到群消息时更新，是 Moonlark 内部最可靠的群列表：QQ 官方机器人
    没有“获取群列表”的接口，只能靠群里真实发生过的消息来发现群聊。

    ``group_key`` 是广播开关使用的归一化群标识：已绑定 OneBot 群号时用群号，
    否则用 QQ 官方 ``group_openid``。
    """

    __tablename__ = "nonebot_plugin_broadcast_group"

    group_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    # 群 QQ 号（OneBot 协议）与群 openid（QQ 官方协议），可能只知其一
    group_qq_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    group_openid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    # 最后一次收到该群消息的时间
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 以下信息来自 GET /v2/groups/{group_openid}/bot_state。
    # 该接口仅对白名单机器人开放（错误码 11253），因此全部允许为空：
    # 为空既表示“没查过”，也表示“查了但没有权限”。
    bot_state_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    allow_proactive_msg: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    recv_msg_setting: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    member_role: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    member_openid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class BroadcastRecord(Model):
    """一次广播的内容快照

    被动补发可能发生在广播提交几分钟之后，届时 ``cached_broadcast_content``
    可能已经被新的广播覆盖，因此每次广播都保留一份内容与按钮快照。
    """

    __tablename__ = "nonebot_plugin_broadcast_record"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text)
    # 按钮的 JSON 快照：[{"label": ..., "text": ...}]
    buttons: Mapped[str] = mapped_column(Text, default="[]")
    submitter: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BroadcastPushEvent(Model):
    """单次广播对单个群聊的推送事件

    ``mode`` 表示计划的推送方式：

    - ``active``：主动消息，广播提交时立即发送；
    - ``passive``：被动消息，QQ 官方机器人未开启主动消息推送时，等该群发来
      下一条消息后延迟三分钟再回复（被动消息必须在收到消息后的一段时间内发送）。

    ``status`` 为 ``pending`` 的 passive 事件会在该群下一次收到消息时被调度。
    """

    __tablename__ = "nonebot_plugin_broadcast_push_event"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(index=True)
    group_key: Mapped[str] = mapped_column(String(128), index=True)
    group_openid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    bot_id: Mapped[str] = mapped_column(String(128))
    adapter: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    # 被动补发所回复的消息 id，便于排查
    passive_msg_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UpdateReadStatus(Model):
    """用户提醒记录：保存每个用户最后阅读的更新公告 ID"""

    __tablename__ = "nonebot_plugin_broadcast_update_read_status"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_update_id: Mapped[int] = mapped_column(default=0)
