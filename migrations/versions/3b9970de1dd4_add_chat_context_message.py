"""add chat context message table

迁移 ID: 3b9970de1dd4
父迁移: 9ba946e2e080
创建时间: 2026-10-06 09:40:00.000000

重写 message queue 的上下文管理（见 src/plugins/nonebot_plugin_chat/core/context.py）：

- 新增 ``nonebot_plugin_chat_contextmessage``：Chat Context 的消息表，
  ``(session_id, context_index, index)`` 复合主键，``block_id`` 标记事件总结的
  block（0 为 system / meta 前导消息），``request_id`` 标记某次 LLM 请求期间产生的消息；
- ``nonebot_plugin_chat_sessionevent`` 增加 ``block_id``：事件总结与消息 block 对应，
  滑动窗口据此按 block 回溯删除历史消息；
- 删除旧的 ``nonebot_plugin_chat_messagequeuecache``：其 message_json + 哈希去重的
  结构无法映射到新表，按约定不做数据迁移，新表冷启动。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "3b9970de1dd4"
down_revision: str | Sequence[str] | None = "9ba946e2e080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONTEXT_TABLE = "nonebot_plugin_chat_contextmessage"
EVENT_TABLE = "nonebot_plugin_chat_sessionevent"
OLD_CACHE_TABLE = "nonebot_plugin_chat_messagequeuecache"


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index_name in [index["name"] for index in inspector.get_indexes(table_name)]


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in [column["name"] for column in inspector.get_columns(table_name)]


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade(name: str = "") -> None:
    if name:
        return
    if not _table_exists(CONTEXT_TABLE):
        op.create_table(
            CONTEXT_TABLE,
            sa.Column("session_id", sa.String(length=128), nullable=False),
            sa.Column("context_index", sa.Integer(), nullable=False),
            sa.Column("index", sa.Integer(), nullable=False),
            sa.Column("block_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("sub_type", sa.String(length=16), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("data", sa.Text(), nullable=True),
            sa.Column("tool_calls", sa.Text(), nullable=True),
            sa.Column("tool_call_id", sa.String(length=64), nullable=True),
            sa.Column("trigger_type", sa.String(length=16), nullable=False),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.PrimaryKeyConstraint(
                "session_id",
                "context_index",
                "index",
                name=op.f("pk_nonebot_plugin_chat_contextmessage"),
            ),
            info={"bind_key": "nonebot_plugin_chat"},
        )
        with op.batch_alter_table(CONTEXT_TABLE, schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_nonebot_plugin_chat_contextmessage_block_id"), ["block_id"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_nonebot_plugin_chat_contextmessage_request_id"), ["request_id"], unique=False
            )

    if not _column_exists(EVENT_TABLE, "block_id"):
        with op.batch_alter_table(EVENT_TABLE, schema=None) as batch_op:
            batch_op.add_column(sa.Column("block_id", sa.Integer(), nullable=False, server_default="0"))
            batch_op.create_index(
                batch_op.f("ix_nonebot_plugin_chat_sessionevent_block_id"), ["block_id"], unique=False
            )

    if _table_exists(OLD_CACHE_TABLE):
        op.drop_table(OLD_CACHE_TABLE)


def downgrade(name: str = "") -> None:
    if name:
        return
    if _table_exists(CONTEXT_TABLE):
        with op.batch_alter_table(CONTEXT_TABLE, schema=None) as batch_op:
            if _index_exists(CONTEXT_TABLE, "ix_nonebot_plugin_chat_contextmessage_request_id"):
                batch_op.drop_index(batch_op.f("ix_nonebot_plugin_chat_contextmessage_request_id"))
            if _index_exists(CONTEXT_TABLE, "ix_nonebot_plugin_chat_contextmessage_block_id"):
                batch_op.drop_index(batch_op.f("ix_nonebot_plugin_chat_contextmessage_block_id"))
        op.drop_table(CONTEXT_TABLE)

    if _column_exists(EVENT_TABLE, "block_id"):
        with op.batch_alter_table(EVENT_TABLE, schema=None) as batch_op:
            if _index_exists(EVENT_TABLE, "ix_nonebot_plugin_chat_sessionevent_block_id"):
                batch_op.drop_index(batch_op.f("ix_nonebot_plugin_chat_sessionevent_block_id"))
            batch_op.drop_column("block_id")

    if not _table_exists(OLD_CACHE_TABLE):
        op.create_table(
            OLD_CACHE_TABLE,
            sa.Column("message_id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("group_id", sa.String(length=128), nullable=False),
            sa.Column("trace_id", sa.String(length=64), nullable=True),
            sa.Column("message_json", sa.Text(), nullable=False),
            sa.Column("updated_time", sa.DateTime(), nullable=False),
            sa.Column("message_hash", sa.BINARY(length=32), nullable=False),
            sa.PrimaryKeyConstraint("message_id", name=op.f("pk_nonebot_plugin_chat_messagequeuecache")),
            info={"bind_key": "nonebot_plugin_chat"},
        )
