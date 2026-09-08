"""add auto sign fields to sign_data

迁移 ID: c8d9e0f1a2b3
父迁移: ffdcbc994500
创建时间: 2026-08-22 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "ffdcbc994500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = {
    "auto_enabled": sa.Column("auto_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    "auto_limit": sa.Column("auto_limit", sa.Integer(), nullable=False, server_default="0"),
    "auto_used": sa.Column("auto_used", sa.Integer(), nullable=False, server_default="0"),
    "auto_count": sa.Column("auto_count", sa.Integer(), nullable=False, server_default="0"),
}


def upgrade(name: str = "") -> None:
    if name:
        return
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("nonebot_plugin_sign_signdata")]
    with op.batch_alter_table("nonebot_plugin_sign_signdata", schema=None) as batch_op:
        for column_name, column in COLUMNS.items():
            if column_name not in columns:
                batch_op.add_column(column)


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_sign_signdata", schema=None) as batch_op:
        for column_name in COLUMNS:
            batch_op.drop_column(column_name)
