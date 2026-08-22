"""Remove chat indexes

迁移 ID: ffdcbc994500
父迁移: ffdcbc994499
创建时间: 2026-08-21 07:15:00.000000

移除 nonebot_plugin_chat 中历史遗留的旧索引。
这些索引是旧版本代码创建的，当前代码已不再使用。
全新部署的数据库不会存在这些索引，因此需要先检查是否存在。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ffdcbc994500"
down_revision: str | Sequence[str] | None = "ffdcbc994499"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _index_exists(connection, table_name: str, index_name: str) -> bool:
    """检查索引是否存在（兼容全新部署）"""
    engine = getattr(connection, "engine", connection)
    insp = sa.inspect(engine)
    indexes = [idx["name"] for idx in insp.get_indexes(table_name)]
    return index_name in indexes


def upgrade(name: str = "") -> None:
    if name:
        return
    conn = op.get_bind()
    if _index_exists(conn, "nonebot_plugin_chat_diaryentry", "ix_agent_event_created_at"):
        op.drop_index("ix_agent_event_created_at", table_name="nonebot_plugin_chat_diaryentry")
    if _index_exists(conn, "nonebot_plugin_chat_note", "ix_note_created_time"):
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
