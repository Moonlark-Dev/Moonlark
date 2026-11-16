"""add chat per-session setting table

迁移 ID: b3c8f1d2e4a6
父迁移: e7a2b9c1d3f4
创建时间: 2026-11-16 13:20:00.000000

``nonebot_plugin_chat_chatsessionsetting``：按会话保存 Chat 设置（键值对），目前
用于区分模型 Provider。复合主键 ``(session_id, key)``；没有记录表示该会话没有单独
设置，跟随 ``ChatGlobalSetting`` 里的全局默认（见 ``utils/provider.py``）。

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c8f1d2e4a6"
down_revision: str | Sequence[str] | None = "e7a2b9c1d3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_chatsessionsetting"


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "key", name=op.f(f"pk_{TABLE_NAME}")),
        info={"bind_key": "nonebot_plugin_chat"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table(TABLE_NAME)
