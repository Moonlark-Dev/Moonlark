"""broadcast group registry, push events and merged update announcement

迁移 ID: b7e4c1a2d9f0
父迁移: 266b039a6ad8, f7b2c8d9e1a3（同时合并这两个迁移头）
创建时间: 2026-11-07 11:30:00.000000

- `nonebot_plugin_broadcast_group`：bc 自己维护的群列表，收到群消息时更新，
  同时保存最后收消息时间与 QQ 官方 bot_state 信息（白名单接口，字段可空）。
- `nonebot_plugin_broadcast_record` / `nonebot_plugin_broadcast_push_event`：
  每次广播的内容快照与逐群推送事件，用于被动消息延迟补发。
- 原 `nonebot_plugin_updates` 插件的已读记录迁移到 broadcast，并删除旧表。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4c1a2d9f0"
down_revision: str | Sequence[str] | None = (
    "266b039a6ad8",
    "f7b2c8d9e1a3",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_READ_STATUS_TABLE = "nonebot_plugin_updates_updatereadstatus"
NEW_READ_STATUS_TABLE = "nonebot_plugin_broadcast_update_read_status"


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_broadcast_group",
        sa.Column("group_key", sa.String(length=128), nullable=False),
        sa.Column("group_qq_number", sa.String(length=64), nullable=True),
        sa.Column("group_openid", sa.String(length=128), nullable=True),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("bot_state_checked_at", sa.DateTime(), nullable=True),
        sa.Column("allow_proactive_msg", sa.Boolean(), nullable=True),
        sa.Column("recv_msg_setting", sa.String(length=32), nullable=True),
        sa.Column("member_role", sa.String(length=16), nullable=True),
        sa.Column("member_openid", sa.String(length=128), nullable=True),
        sa.Column("joined_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("group_key", name=op.f("pk_nonebot_plugin_broadcast_group")),
        info={"bind_key": "nonebot_plugin_broadcast"},
    )
    with op.batch_alter_table("nonebot_plugin_broadcast_group", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nonebot_plugin_broadcast_group_group_qq_number"), ["group_qq_number"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_nonebot_plugin_broadcast_group_group_openid"), ["group_openid"], unique=False
        )

    op.create_table(
        "nonebot_plugin_broadcast_record",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("buttons", sa.Text(), nullable=False),
        sa.Column("submitter", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nonebot_plugin_broadcast_record")),
        info={"bind_key": "nonebot_plugin_broadcast"},
    )

    op.create_table(
        "nonebot_plugin_broadcast_push_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("broadcast_id", sa.Integer(), nullable=False),
        sa.Column("group_key", sa.String(length=128), nullable=False),
        sa.Column("group_openid", sa.String(length=128), nullable=True),
        sa.Column("bot_id", sa.String(length=128), nullable=False),
        sa.Column("adapter", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("passive_msg_id", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nonebot_plugin_broadcast_push_event")),
        info={"bind_key": "nonebot_plugin_broadcast"},
    )
    with op.batch_alter_table("nonebot_plugin_broadcast_push_event", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nonebot_plugin_broadcast_push_event_broadcast_id"), ["broadcast_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_nonebot_plugin_broadcast_push_event_group_key"), ["group_key"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_nonebot_plugin_broadcast_push_event_status"), ["status"], unique=False)

    op.create_table(
        NEW_READ_STATUS_TABLE,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("last_update_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f(f"pk_{NEW_READ_STATUS_TABLE}")),
        info={"bind_key": "nonebot_plugin_broadcast"},
    )

    # 旧 updates 插件的已读记录：先复制再删除旧表（生产环境已有数据）
    bind = op.get_bind()
    if OLD_READ_STATUS_TABLE in sa.inspect(bind).get_table_names():
        op.execute(
            f"INSERT INTO {NEW_READ_STATUS_TABLE} (user_id, last_update_id) "
            f"SELECT user_id, last_update_id FROM {OLD_READ_STATUS_TABLE}"
        )
        op.drop_table(OLD_READ_STATUS_TABLE)


def downgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        OLD_READ_STATUS_TABLE,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("last_update_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f(f"pk_{OLD_READ_STATUS_TABLE}")),
        info={"bind_key": "nonebot_plugin_updates"},
    )
    bind = op.get_bind()
    if NEW_READ_STATUS_TABLE in sa.inspect(bind).get_table_names():
        op.execute(
            f"INSERT INTO {OLD_READ_STATUS_TABLE} (user_id, last_update_id) "
            f"SELECT user_id, last_update_id FROM {NEW_READ_STATUS_TABLE}"
        )
    op.drop_table(NEW_READ_STATUS_TABLE)
    op.drop_table("nonebot_plugin_broadcast_push_event")
    op.drop_table("nonebot_plugin_broadcast_record")
    op.drop_table("nonebot_plugin_broadcast_group")
