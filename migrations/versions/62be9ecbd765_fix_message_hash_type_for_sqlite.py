"""fix message_hash column type for SQLite

迁移 ID: 62be9ecbd765
父迁移: 02b1cfe2ff47
创建时间: 2026-06-05 23:09:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import LargeBinary

revision: str = "62be9ecbd765"
down_revision: str | Sequence[str] | None = "02b1cfe2ff47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    # 获取当前数据库方言
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        # SQLite 不支持 BINARY，sa.BINARY(32) 会被映射为 NUMERIC 亲和性
        # 需要改为 LargeBinary(32) 以获得正确的 BLOB 亲和性
        with op.batch_alter_table("nonebot_plugin_chat_messagequeuecache", schema=None) as batch_op:
            batch_op.alter_column(
                "message_hash",
                existing_type=sa.NUMERIC(precision=32),
                type_=LargeBinary(32),
                existing_nullable=False,
            )
    # MySQL 已经是 BINARY(32)，无需操作


def downgrade(name: str = "") -> None:
    if name:
        return
    # 获取当前数据库方言
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("nonebot_plugin_chat_messagequeuecache", schema=None) as batch_op:
            batch_op.alter_column(
                "message_hash",
                existing_type=LargeBinary(32),
                type_=sa.NUMERIC(precision=32),
                existing_nullable=False,
            )
    # MySQL 不需要操作
