"""merge heads and add private chat stream mode

合并群聊回复增强（619748a690eb）与模拟股票市场（b836ade52b29）引入的两个迁移头，
恢复单一迁移历史；同时给 ``nonebot_plugin_chat_privatechatconfig`` 添加 ``stream``
列：私聊流式发送开关，默认开启，与 ``gal_mode`` 互斥（见 ``core/stream_mode.py``）。

迁移 ID: 3f9a2c7d5e1b
父迁移: 619748a690eb, b836ade52b29
创建时间: 2026-11-21 14:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "3f9a2c7d5e1b"
down_revision: str | Sequence[str] | None = (
    "619748a690eb",
    "b836ade52b29",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_privatechatconfig"
COLUMN_NAME = "stream"


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
                sa.Column(COLUMN_NAME, sa.Boolean(), nullable=False, server_default=sa.true()),
            )
    _disable_stream_for_gal_mode_users()


def _disable_stream_for_gal_mode_users() -> None:
    """流式发送与私聊备选回复互斥：迁移后把已开启备选回复的用户统一关掉流式发送"""
    inspector = inspect(op.get_bind())
    if TABLE_NAME not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    if not {"stream", "gal_mode"}.issubset(columns):
        return
    op.get_bind().execute(sa.text(f"UPDATE {TABLE_NAME} SET stream = 0 WHERE gal_mode = 1"))


def downgrade(name: str = "") -> None:
    if name:
        return
    if _column_exists():
        with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
            batch_op.drop_column(COLUMN_NAME)
