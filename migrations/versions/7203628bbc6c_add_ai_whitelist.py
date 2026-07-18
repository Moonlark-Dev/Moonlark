"""add_ai_whitelist

迁移 ID: 7203628bbc6c
父迁移: ffdcbc994494
创建时间: 2026-07-17 15:11:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7203628bbc6c"
down_revision: str | Sequence[str] | None = "ffdcbc994494"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_openai_aiwhitelist",
        sa.Column("group_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("group_id", name=op.f("pk_nonebot_plugin_openai_aiwhitelist")),
        info={"bind_key": "nonebot_plugin_openai"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_openai_aiwhitelist")
