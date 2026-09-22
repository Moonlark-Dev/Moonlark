"""add egg selection table

迁移 ID: b5c6d7e8f9a1
父迁移: b3c4d5e6f7a8
创建时间: 2026-08-04 18:30:00.000000

新增用户默认鸡蛋种类选择表，用于 /splat switch 保存每个用户的鸡蛋种类偏好。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b5c6d7e8f9a1"
down_revision: str | Sequence[str] | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_eggstrike_eggselection"


def upgrade(name: str = "") -> None:
    if name:
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("egg_id", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade(name: str = "") -> None:
    if name:
        return

    op.drop_table(TABLE_NAME)
