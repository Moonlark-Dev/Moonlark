"""Add luck trend table.

迁移 ID: 0189a0b1c2d3
父迁移: ffdcbc994498
创建时间: 2026-07-24 18:31:00.000000

"""

# pylint: disable=invalid-name

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0189a0b1c2d3"
down_revision: str | Sequence[str] | None = ("ffdcbc994498",)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_jrrp_lucktrend"


def upgrade(name: str = "") -> None:
    """创建 LuckTrend 表（如尚不存在）."""
    if name:
        return

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "mysql":
        table_check = sa.text("SHOW TABLES LIKE :table_name")
        result = bind.execute(table_check.bindparams(table_name=TABLE_NAME)).fetchall()
    else:
        table_check = sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name = :table_name")
        result = bind.execute(table_check.bindparams(table_name=TABLE_NAME)).fetchall()
    if result:
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("luck_value", sa.Integer(), nullable=False),
        sa.Column("reroll_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("user_id", "record_date", name=op.f("pk_nonebot_plugin_jrrp_lucktrend")),
    )


def downgrade(name: str = "") -> None:
    """删除 LuckTrend 表."""
    if name:
        return
    op.drop_table(TABLE_NAME)
