"""add Timer table for persistent LLM timers

迁移 ID: c3d4e5f6a7b8
父迁移: b4c5d6e7f8a9
创建时间: 2026-06-18 20:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_timer"


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
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("trigger_time", sa.DateTime(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.create_index(f"ix_{TABLE_NAME}_session_id", ["session_id"])
        batch_op.create_index(f"ix_{TABLE_NAME}_trigger_time", ["trigger_time"])


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_index(f"ix_{TABLE_NAME}_session_id")
        batch_op.drop_index(f"ix_{TABLE_NAME}_trigger_time")
    op.drop_table(TABLE_NAME)
