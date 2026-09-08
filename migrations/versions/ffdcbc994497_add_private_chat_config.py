"""add PrivateChatConfig table

迁移 ID: ffdcbc994497
父迁移: ffdcbc994496
创建时间: 2026-07-17 23:55:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "ffdcbc994497"
down_revision: str | Sequence[str] | None = "ffdcbc994496"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_chat_privatechatconfig",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_nonebot_plugin_chat_privatechatconfig")),
        info={"bind_key": "nonebot_plugin_chat"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_chat_privatechatconfig")
