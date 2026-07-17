"""remove InstantMemoryCache table

迁移 ID: ffdcbc994495
父迁移: ffdcbc994494
创建时间: 2026-07-17 17:15:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "ffdcbc994495"
down_revision: str | Sequence[str] | None = "ffdcbc994494"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_chat_instantmemorycache")


def downgrade(name: str = "") -> None:
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
