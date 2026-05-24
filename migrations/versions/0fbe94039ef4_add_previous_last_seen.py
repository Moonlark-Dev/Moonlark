"""add previous_last_seen to LastSeenRecord

迁移 ID: 0fbe94039ef4
父迁移: a280bc2d
创建时间: 2026-05-24 22:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0fbe94039ef4"
down_revision: str | Sequence[str] | None = "ebd58910367a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_last_seen_lastseenrecord", schema=None) as batch_op:
        batch_op.add_column(sa.Column("previous_last_seen", sa.DateTime(), nullable=True))


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_last_seen_lastseenrecord", schema=None) as batch_op:
        batch_op.drop_column("previous_last_seen")
