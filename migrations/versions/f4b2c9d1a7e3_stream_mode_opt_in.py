"""private chat stream mode is experimental and opt-in

私聊流式发送（``/chat stream``）改为实验性功能、默认关闭：

- 把 ``nonebot_plugin_chat_privatechatconfig.stream`` 的 server_default 从 true
  改为 false；
- 把已有记录统一关闭。该功能此前默认开启（用户没有主动选择过就会是 true），
  改成实验性功能后需要用户用 ``/chat stream on`` 显式开启。

表或列不存在时（跳过了旧迁移的数据库）迁移直接跳过，不报错。

迁移 ID: f4b2c9d1a7e3
父迁移: c8d5e3b02f74
创建时间: 2026-11-22 00:50:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "f4b2c9d1a7e3"
down_revision: str | Sequence[str] | None = "c8d5e3b02f74"
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


def _set_stream_default(value: bool) -> None:
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.alter_column(
            COLUMN_NAME,
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=sa.true() if value else sa.false(),
        )


def _update_stream(value: bool) -> None:
    config_table = sa.table(TABLE_NAME, sa.column(COLUMN_NAME, sa.Boolean()))
    op.get_bind().execute(config_table.update().values({COLUMN_NAME: sa.true() if value else sa.false()}))


def upgrade(name: str = "") -> None:
    if name:
        return
    if not _column_exists():
        return
    _set_stream_default(False)
    _update_stream(False)


def downgrade(name: str = "") -> None:
    if name:
        return
    if not _column_exists():
        return
    _set_stream_default(True)
    _update_stream(True)
