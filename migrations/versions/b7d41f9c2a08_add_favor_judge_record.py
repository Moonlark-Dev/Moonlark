"""add favor judge record

迁移 ID: b7d41f9c2a08
父迁移: 398dc14b670d
创建时间: 2026-10-07 12:00:00.000000

好感度评价的冷却数据不再存放在 LarkUser 的 config（``chat_fav_judge_cache``）里，
改为每次评价都写一条 ``nonebot_plugin_chat_favorjudgerecord``：

- 冷却时间与每日上限由本表推导；
- ``message_key`` 保存消息指纹（<=5 字为原文，>5 字为 simhash），
  同一条消息被反复发送时据此抬高 Jev 判定「提升好感度」所需的置信度。

旧数据不迁移：config 里的缓存只有一个时间戳和一个累计值，没有消息内容，
无法重建历史记录，冷却窗口本身也只有一小时。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b7d41f9c2a08"
down_revision: str | Sequence[str] | None = "398dc14b670d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_favorjudgerecord"
INDEXED_COLUMNS = ("created_at", "session_id", "user_id")


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("nickname", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("message_key", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE_NAME}")),
        info={"bind_key": "nonebot_plugin_chat"},
    )
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        for column_name in INDEXED_COLUMNS:
            batch_op.create_index(batch_op.f(f"ix_{TABLE_NAME}_{column_name}"), [column_name], unique=False)


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        for column_name in INDEXED_COLUMNS:
            batch_op.drop_index(batch_op.f(f"ix_{TABLE_NAME}_{column_name}"))

    op.drop_table(TABLE_NAME)
