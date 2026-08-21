"""add downed_at to UserData and UserDeathRecord table

迁移 ID: a9e4b2c8f1d6
父迁移: a8f3c1d2e4b5
创建时间: 2026-08-02 15:22:23.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "a9e4b2c8f1d6"
down_revision: str | Sequence[str] | None = "a8f3c1d2e4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_larkuser_userdeathrecord"
DATA_TABLE = "nonebot_plugin_larkuser_userdata"


def upgrade(name: str = "") -> None:
    if name:
        return
    conn = op.get_bind()
    inspector = inspect(conn)

    columns = [c["name"] for c in inspector.get_columns(DATA_TABLE)]
    if "downed_at" not in columns:
        with op.batch_alter_table(DATA_TABLE, schema=None) as batch_op:
            batch_op.add_column(sa.Column("downed_at", sa.DateTime(), nullable=True))

    existing_tables = inspector.get_table_names()
    if TABLE_NAME not in existing_tables:
        op.create_table(
            TABLE_NAME,
            sa.Column("user_id", sa.String(length=128), nullable=False),
            sa.Column("death_count", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("user_id", name=op.f("pk_nonebot_plugin_larkuser_userdeathrecord")),
            info={"bind_key": "nonebot_plugin_larkuser"},
        )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table(TABLE_NAME)
    with op.batch_alter_table(DATA_TABLE, schema=None) as batch_op:
        batch_op.drop_column("downed_at")
