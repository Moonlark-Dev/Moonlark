"""add AIWhitelist table

迁移 ID: ffdcbc994496
父迁移: ffdcbc994495
创建时间: 2026-07-17 20:15:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "ffdcbc994496"
down_revision: str | Sequence[str] | None = "ffdcbc994495"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_openai_aiwhitelist",
        sa.Column("group_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("group_id", name=op.f("pk_nonebot_plugin_openai_aiwhitelist")),
        info={"bind_key": "nonebot_plugin_openai"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_openai_aiwhitelist")
