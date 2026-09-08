"""Add record_date to chatterbox ranking table

迁移 ID: 991019747839
父迁移: 0189a0b1c2d3
创建时间: 2026-08-02 00:00:00.000000

为话痨排行添加按天统计支持，旧累计数据清空重新统计。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "991019747839"
down_revision: str | Sequence[str] | None = "0189a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "nonebot_plugin_chatterbox_ranking_groupchatterbox"


def upgrade(name: str = "") -> None:
    """删除旧累计表并重建为按天统计表"""
    if name:
        return
    op.drop_table(TABLE_NAME)
    op.create_table(
        TABLE_NAME,
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("group_id", sa.String(length=128), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id_", name=op.f("pk_nonebot_plugin_chatterbox_ranking_groupchatterbox")),
        info={"bind_key": "nonebot_plugin_chatterbox_ranking"},
    )


def downgrade(name: str = "") -> None:
    """回退为旧的累计表结构"""
    if name:
        return
    op.drop_table(TABLE_NAME)
    op.create_table(
        TABLE_NAME,
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("group_id", sa.String(length=128), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id_", name=op.f("pk_nonebot_plugin_chatterbox_ranking_groupchatterbox")),
        info={"bind_key": "nonebot_plugin_chatterbox_ranking"},
    )
