"""add updates read status

迁移 ID: 447403958b5a
父迁移: f2a96c4be153
创建时间: 2026-10-14 23:33:31.303931

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "447403958b5a"
down_revision: str | Sequence[str] | None = "f2a96c4be153"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_updates_updatereadstatus",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("last_update_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_nonebot_plugin_updates_updatereadstatus")),
        info={"bind_key": "nonebot_plugin_updates"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_updates_updatereadstatus")
