"""add message_hash to GroupMessage

迁移 ID: 7f8a9b0c1d2e
父迁移: ffdcbc994494
创建时间: 2026-07-04 20:30:00
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "7f8a9b0c1d2e"
down_revision: str | Sequence[str] | None = "ffdcbc994494"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade(name: str = "") -> None:
    if name:
        return
    op.add_column(
        "nonebot_plugin_message_summary_groupmessage",
        sa.Column("message_hash", sa.BINARY(32), nullable=True),
    )

def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_column("nonebot_plugin_message_summary_groupmessage", "message_hash")
