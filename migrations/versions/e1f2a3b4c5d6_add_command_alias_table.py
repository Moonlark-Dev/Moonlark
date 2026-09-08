"""Add command alias table

迁移 ID: e1f2a3b4c5d6
父迁移: d4e5f6a7b8c9
创建时间: 2026-08-03 09:30:00.000000

为指令别名功能（issue #1328）创建用户指令别名表
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_command_alias"


def upgrade(name: str = "") -> None:
    if name:
        return

    # 创建指令别名表（用户ID + 别名 复合主键）
    op.create_table(
        TABLE_NAME,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("command", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "alias"),
    )


def downgrade(name: str = "") -> None:
    if name:
        return

    # 删除指令别名表
    op.drop_table(TABLE_NAME)
