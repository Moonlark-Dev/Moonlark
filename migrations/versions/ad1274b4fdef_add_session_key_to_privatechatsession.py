"""add session_key to PrivateChatSession

迁移 ID: ad1274b4fdef
父迁移: 0c7846aeaa7b
创建时间: 2026-05-18 19:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "ad1274b4fdef"
down_revision: str | Sequence[str] | None = "0c7846aeaa7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_chat_privatechatsession", schema=None) as batch_op:
        batch_op.add_column(sa.Column("session_key", sa.String(length=256), nullable=True))


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_chat_privatechatsession", schema=None) as batch_op:
        batch_op.drop_column("session_key")
