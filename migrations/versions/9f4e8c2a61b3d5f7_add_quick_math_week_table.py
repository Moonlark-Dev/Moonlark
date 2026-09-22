"""add quick math weekly score table

迁移 ID: 9f4e8c2a61b3d5f7
父迁移: cdf298a5eb8b
创建时间: 2026-09-08 12:00:00.000000

为 Quick Math 主界面周积分排行榜新增按 ISO 周累计的积分表。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "9f4e8c2a61b3d5f7"
down_revision: str | Sequence[str] | None = "cdf298a5eb8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_quick_math_quickmathweek"


def upgrade(name: str = "") -> None:
    if name:
        return

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "mysql":
        table_check = sa.text("SHOW TABLES LIKE :table_name")
    else:
        table_check = sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name")
    result = bind.execute(table_check, {"table_name": TABLE_NAME}).fetchall()
    if result:
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("week", sa.String(length=16), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "week", name=op.f("pk_nonebot_plugin_quick_math_quickmathweek")),
        info={"bind_key": "nonebot_plugin_quick_math"},
    )
    op.create_index(
        op.f("ix_nonebot_plugin_quick_math_quickmathweek_week"),
        TABLE_NAME,
        ["week"],
        unique=False,
        info={"bind_key": "nonebot_plugin_quick_math"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_index(op.f("ix_nonebot_plugin_quick_math_quickmathweek_week"), table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
