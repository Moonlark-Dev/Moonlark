"""add interaction_mode to chat_group

迁移 ID: a8f3c1d2e4b5
父迁移: ffdcbc994499
创建时间: 2026-05-20 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a8f3c1d2e4b5"
down_revision: str | Sequence[str] | None = "ffdcbc994499"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_chat_chatgroup", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("interaction_mode", sa.String(length=16), nullable=False, server_default="standard")
        )


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_chat_chatgroup", schema=None) as batch_op:
        batch_op.drop_column("interaction_mode")
