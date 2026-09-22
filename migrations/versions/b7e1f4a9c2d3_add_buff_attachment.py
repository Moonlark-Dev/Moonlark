"""Add buff attachment table

迁移 ID: b7e1f4a9c2d3
父迁移: f0a1b2c3d4e5
创建时间: 2026-09-21 00:10:00.000000

新增效果（Buff）系统，用于存储、管理用户当前具有的效果：
- nonebot_plugin_buff_attachment：每个用户 + 每个 buff 一行，
  记录层数、到期时间（时间维度）与剩余次数（次数维度）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e1f4a9c2d3"
down_revision: str | Sequence[str] | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_buff_attachment"


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("buff_id", sa.String(length=128), nullable=False),
        sa.Column("layers", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("remaining_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id_", name=op.f(f"pk_{TABLE_NAME}")),
        sa.UniqueConstraint("user_id", "buff_id", name="uq_nonebot_plugin_buff_attachment_user_buff"),
        info={"bind_key": "nonebot_plugin_buff"},
    )
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.create_index(batch_op.f(f"ix_{TABLE_NAME}_user_id"), ["user_id"], unique=False)
        batch_op.create_index(batch_op.f(f"ix_{TABLE_NAME}_buff_id"), ["buff_id"], unique=False)


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_index(batch_op.f(f"ix_{TABLE_NAME}_buff_id"))
        batch_op.drop_index(batch_op.f(f"ix_{TABLE_NAME}_user_id"))

    op.drop_table(TABLE_NAME)
