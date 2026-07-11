"""add wakeuprank risedata table

迁移 ID: 878331db0e57
父迁移: c3d4e5f6a7b8
创建时间: 2026-07-11 19:59:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "878331db0e57"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_wakeuprank_risedata"


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
        sa.Column("wake_time", sa.DateTime(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "record_date", name=op.f("pk_nonebot_plugin_wakeuprank_risedata")),
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table(TABLE_NAME)
