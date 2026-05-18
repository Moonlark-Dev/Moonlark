"""empty message

迁移 ID: ebd58910367a
父迁移: e7f8a9b0c1d2
创建时间: 2026-05-18 23:28:42.316324

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy import inspect

revision: str = 'ebd58910367a'
down_revision: str | Sequence[str] | None = 'e7f8a9b0c1d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    # 处理 InstantMemoryCache 表（可能不存在）
    if 'nonebot_plugin_chat_instantmemorycache' in tables:
        existing_indexes = {
            idx['name'] for idx in inspector.get_indexes('nonebot_plugin_chat_instantmemorycache')
        }
        with op.batch_alter_table('nonebot_plugin_chat_instantmemorycache', schema=None) as batch_op:
            if 'ix_instantmemorycache_expire_time' in existing_indexes:
                batch_op.drop_index('ix_instantmemorycache_expire_time')
            if 'ix_instantmemorycache_session_id' in existing_indexes:
                batch_op.drop_index('ix_instantmemorycache_session_id')
            if 'ix_nonebot_plugin_chat_instantmemorycache_session_id' not in existing_indexes:
                batch_op.create_index(
                    'ix_nonebot_plugin_chat_instantmemorycache_session_id',
                    ['session_id'],
                    unique=False,
                )

    # 处理 PrivateChatSession 表
    if 'nonebot_plugin_chat_privatechatsession' in tables:
        # 清空旧数据（session_key 格式已变更，旧数据无意义）
        conn.execute(sa.text("DELETE FROM nonebot_plugin_chat_privatechatsession"))

        with op.batch_alter_table('nonebot_plugin_chat_privatechatsession', schema=None) as batch_op:
            batch_op.alter_column(
                'session_key',
                existing_type=mysql.VARCHAR(length=256),
                nullable=False,
            )


def downgrade(name: str = "") -> None:
    if name:
        return

    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if 'nonebot_plugin_chat_privatechatsession' in tables:
        with op.batch_alter_table('nonebot_plugin_chat_privatechatsession', schema=None) as batch_op:
            batch_op.alter_column(
                'session_key',
                existing_type=mysql.VARCHAR(length=256),
                nullable=True,
            )

    if 'nonebot_plugin_chat_instantmemorycache' in tables:
        existing_indexes = {
            idx['name'] for idx in inspector.get_indexes('nonebot_plugin_chat_instantmemorycache')
        }
        with op.batch_alter_table('nonebot_plugin_chat_instantmemorycache', schema=None) as batch_op:
            if 'ix_nonebot_plugin_chat_instantmemorycache_session_id' in existing_indexes:
                batch_op.drop_index('ix_nonebot_plugin_chat_instantmemorycache_session_id')
            if 'ix_instantmemorycache_session_id' not in existing_indexes:
                batch_op.create_index('ix_instantmemorycache_session_id', ['session_id'], unique=False)
            if 'ix_instantmemorycache_expire_time' not in existing_indexes:
                batch_op.create_index('ix_instantmemorycache_expire_time', ['expire_time'], unique=False)
