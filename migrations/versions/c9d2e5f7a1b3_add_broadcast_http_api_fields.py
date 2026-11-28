"""add broadcast http api fields

广播 HTTP 接口（``POST /api/broadcast``）需要在 ``nonebot_plugin_broadcast_record``
上记录处理状态与目标数量，并支持 ``Idempotency-Key``：

- ``request_id``：HTTP 幂等键（唯一索引），同一个键只产生一次广播；
- ``request_hash``：请求指纹，同一个幂等键配了不同内容时拒绝请求；
- ``status``：queued/running/done/failed，供状态查询与「单并发」判断；
- ``total``：计划推送的群数。

存量记录都是同步提交的旧广播，``status`` 直接视为 ``done``。

同时合并 main 上遗留的三个迁移头（d3e5f7a9b1c2、f4b2c9d1a7e3、84571e1c35bd），迁移后保持单头。

迁移 ID: c9d2e5f7a1b3
父迁移: d3e5f7a9b1c2, f4b2c9d1a7e3, 84571e1c35bd
创建时间: 2026-11-29 02:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "c9d2e5f7a1b3"
down_revision: str | Sequence[str] | None = ("d3e5f7a9b1c2", "f4b2c9d1a7e3", "84571e1c35bd")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "nonebot_plugin_broadcast_record"
INDEX = "ix_nonebot_plugin_broadcast_record_request_id"
COLUMNS = {
    "request_id": sa.Column("request_id", sa.String(length=64), nullable=True),
    "request_hash": sa.Column("request_hash", sa.String(length=64), nullable=True),
    "status": sa.Column("status", sa.String(length=16), nullable=False, server_default="done"),
    "total": sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
}


def _get_columns() -> list[str]:
    inspector = inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return []
    return [column["name"] for column in inspector.get_columns(TABLE)]


def _index_exists() -> bool:
    inspector = inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return False
    return any(index["name"] == INDEX for index in inspector.get_indexes(TABLE))


def upgrade(name: str = "") -> None:
    if name:
        return
    columns = _get_columns()
    if not columns:
        return
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for column_name, column in COLUMNS.items():
            if column_name not in columns:
                batch_op.add_column(column)
    if not _index_exists():
        op.create_index(INDEX, TABLE, ["request_id"], unique=True)


def downgrade(name: str = "") -> None:
    if name:
        return
    columns = _get_columns()
    if not columns:
        return
    if _index_exists():
        op.drop_index(INDEX, table_name=TABLE)
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for column_name in COLUMNS:
            if column_name in columns:
                batch_op.drop_column(column_name)
