"""add InstantMemoryCache

迁移 ID: e7f8a9b0c1d2
父迁移: ad1274b4fdef
创建时间: 2026-05-18 19:35:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "ad1274b4fdef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_chat_instantmemorycache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.Column("expire_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("nonebot_plugin_chat_instantmemorycache", schema=None) as batch_op:
        batch_op.create_index("ix_instantmemorycache_session_id", ["session_id"])
        batch_op.create_index("ix_instantmemorycache_expire_time", ["expire_time"])


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_chat_instantmemorycache")
