"""给 PrivateChatConfig 添加 gal_mode

迁移 ID: ffdcbc994501
父迁移: b7e4c1a2d9f0
创建时间: 2026-11-10 10:00:00.000000

nonebot_plugin_chat_privatechatconfig.gal_mode：私聊备选回复开关，默认关闭。
开关打开后私聊回复会延迟一条发送，并在每轮结束时附带生成的备选回复按钮
（见 core/gal_mode.py）。

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "ffdcbc994501"
down_revision: str | Sequence[str] | None = "b7e4c1a2d9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_privatechatconfig"
COLUMN_NAME = "gal_mode"


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
