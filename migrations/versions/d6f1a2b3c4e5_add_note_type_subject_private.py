"""add note type, subject and private columns

迁移 ID: d6f1a2b3c4e5
父迁移: a7c3e5f9b1d4
创建时间: 2026-11-14 22:35:00.000000

给笔记增加记忆类型（type）、中心词（subject）和私密标记（private）。

旧的笔记没有这些信息，无法参与新的类型化召回，按需求直接清空（不迁移老笔记）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op
import sqlalchemy as sa

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d6f1a2b3c4e5"
down_revision: str | Sequence[str] | None = "a7c3e5f9b1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTE_TABLE = "nonebot_plugin_chat_note"


def upgrade(name: str = "") -> None:
    if name:
        return

    with op.batch_alter_table(NOTE_TABLE, schema=None) as batch_op:
        batch_op.add_column(sa.Column("type", sa.String(length=16), server_default="event", nullable=False))
        batch_op.add_column(sa.Column("subject", sa.String(length=256), server_default="", nullable=False))
        batch_op.add_column(sa.Column("private", sa.Boolean(), server_default=sa.false(), nullable=False))

    # 旧笔记没有 type / subject，直接删除，不做数据迁移
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute("TRUNCATE TABLE nonebot_plugin_chat_note")
    else:
        op.execute("DELETE FROM nonebot_plugin_chat_note")


def downgrade(name: str = "") -> None:
    if name:
        return

    with op.batch_alter_table(NOTE_TABLE, schema=None) as batch_op:
        batch_op.drop_column("private")
        batch_op.drop_column("subject")
        batch_op.drop_column("type")
