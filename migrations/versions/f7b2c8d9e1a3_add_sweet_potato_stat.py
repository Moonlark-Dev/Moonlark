"""add sweet potato stat table and merge migration heads

迁移 ID: f7b2c8d9e1a3
父迁移: 447403958b5a, c6f8a1d2e3b4, e4c1a95f02bd
创建时间: 2026-10-30 21:30:00.000000

新增烫手山芋玩法的排行数据表，同时合并主分支遗留的三个迁移头：
- 447403958b5a add updates read status
- c6f8a1d2e3b4 add craft & equip tables and merge migration heads
- e4c1a95f02bd remove openai history record
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7b2c8d9e1a3"
down_revision: str | Sequence[str] | None = (
    "447403958b5a",
    "c6f8a1d2e3b4",
    "e4c1a95f02bd",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_sweet_potato_stat",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("successful_holds", sa.Integer(), nullable=False),
        sa.Column("total_holds", sa.Integer(), nullable=False),
        sa.Column("total_passes", sa.Integer(), nullable=False),
        sa.Column("burn_count", sa.Integer(), nullable=False),
        sa.Column("game_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_nonebot_plugin_sweet_potato_stat")),
        info={"bind_key": "nonebot_plugin_sweet_potato"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_sweet_potato_stat")
