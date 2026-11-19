"""给 ChatGroup 添加 enhance

迁移 ID: 619748a690eb
父迁移: b3c8f1d2e4a6
创建时间: 2026-11-18 23:05:00.000000

nonebot_plugin_chat_chatgroup.enhance：群聊回复增强开关，默认关闭。
开关打开后 Moonlark 发送的每条消息都会先按当前 Chat 提示词与最近对话重写一次
（仅 OpenAI Provider 生效，见 core/enhance.py）。

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "619748a690eb"
down_revision: str | Sequence[str] | None = "b3c8f1d2e4a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_chatgroup"
COLUMN_NAME = "enhance"


def _column_exists() -> bool:
    """表或列不存在时返回 False（兼容跳过了旧迁移的数据库）"""
    inspector = inspect(op.get_bind())
    if TABLE_NAME not in inspector.get_table_names():
        return False
    return COLUMN_NAME in {column["name"] for column in inspector.get_columns(TABLE_NAME)}


def upgrade(name: str = "") -> None:
    if name:
        return
    if not _column_exists():
        with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(COLUMN_NAME, sa.Boolean(), nullable=False, server_default=sa.false()),
            )


def downgrade(name: str = "") -> None:
    if name:
        return
    if _column_exists():
        with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
            batch_op.drop_column(COLUMN_NAME)
