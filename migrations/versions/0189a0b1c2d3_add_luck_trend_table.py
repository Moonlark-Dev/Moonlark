"""add luck trend table

迁移 ID: 0189a0b1c2d3
父迁移: ffdcbc994498
创建时间: 2026-07-24 18:31:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0189a0b1c2d3"
down_revision: str | Sequence[str] | None = (
    "ffdcbc994498",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_jrrp_lucktrend"


def upgrade(name: str = "") -> None:
    if name:
        return

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "mysql":
        table_check = f"SHOW TABLES LIKE '{TABLE_NAME}'"
    else:
        table_check = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_NAME}'"
    result = bind.execute(sa.text(table_check)).fetchall()
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
    if name:
        return
    op.drop_table(TABLE_NAME)
