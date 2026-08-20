"""Remove chat indexes

迁移 ID: ffdcbc994500
父迁移: ffdcbc994499
创建时间: 2026-08-21 07:15:00.000000

移除 nonebot_plugin_chat 中不再需要的索引
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "ffdcbc994500"
down_revision: str | Sequence[str] | None = "ffdcbc994499"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.drop_index("ix_agent_event_created_at", table_name="nonebot_plugin_chat_diaryentry")
    op.drop_index("ix_note_created_time", table_name="nonebot_plugin_chat_note")


def downgrade(name: str = "") -> None:
    if name:
        return
    op.create_index(
        "ix_agent_event_created_at",
        "nonebot_plugin_chat_diaryentry",
        ["created_at"],
    )
    op.create_index(
        "ix_note_created_time",
        "nonebot_plugin_chat_note",
        ["created_time"],
    )
