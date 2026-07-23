"""为 Note.created_time 添加索引

迁移 ID: ffdcbc994498
父迁移: 3ee8b001fa91
创建时间: 2026-07-23 18:50:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "ffdcbc994498"
down_revision: str | Sequence[str] | None = "3ee8b001fa91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_chat_note", schema=None) as batch_op:
        batch_op.create_index("ix_note_created_time", ["created_time"])


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_chat_note", schema=None) as batch_op:
        batch_op.drop_index("ix_note_created_time")
