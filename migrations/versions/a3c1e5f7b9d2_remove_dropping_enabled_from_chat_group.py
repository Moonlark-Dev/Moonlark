"""remove dropping_enabled from chat_group

迁移 ID: a3c1e5f7b9d2
父迁移: 62be9ecbd765
创建时间: 2026-07-26 17:50:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a3c1e5f7b9d2"
down_revision: str | Sequence[str] | None = "62be9ecbd765"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_chat_chatgroup", schema=None) as batch_op:
        batch_op.drop_column("dropping_enabled")


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_chat_chatgroup", schema=None) as batch_op:
        batch_op.add_column(sa.Column("dropping_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")))
