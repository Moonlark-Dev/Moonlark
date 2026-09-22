"""add proactive chat record table

迁移 ID: b7d21f4c9a05
父迁移: a7f3c9e21b64
创建时间: 2026-09-16 17:47:28.000000

为 chat 插件新增主动私聊发送记录表：
- nonebot_plugin_chat_proactivechatrecord：记录每次主动私聊的目标、昵称与内容，
  供主动私聊决策（Decide）参考最近若干次发送情况。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b7d21f4c9a05"
down_revision: str | Sequence[str] | None = "a7f3c9e21b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_proactivechatrecord"


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("nickname", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nonebot_plugin_chat_proactivechatrecord")),
        info={"bind_key": "nonebot_plugin_chat"},
    )
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nonebot_plugin_chat_proactivechatrecord_sent_at"), ["sent_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_nonebot_plugin_chat_proactivechatrecord_user_id"), ["user_id"], unique=False
        )


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nonebot_plugin_chat_proactivechatrecord_user_id"))
        batch_op.drop_index(batch_op.f("ix_nonebot_plugin_chat_proactivechatrecord_sent_at"))

    op.drop_table(TABLE_NAME)
