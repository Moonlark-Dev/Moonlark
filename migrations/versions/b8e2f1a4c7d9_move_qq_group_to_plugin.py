"""move qq group tables to nonebot_plugin_qq_group and add platform_user_id

迁移 ID: b8e2f1a4c7d9
父迁移: 398dc14b670d
创建时间: 2026-02-14 12:00:00.000000

两处改动：

1. QQ 官方 Bot 的群聊缓存从 ``nonebot_plugin_larkuser`` 独立为
   ``nonebot_plugin_qq_group`` 插件，对应两张表改名为
   ``nonebot_plugin_qq_group_info`` / ``nonebot_plugin_qq_group_member``
   （只改名，数据保留）；
2. ``nonebot_plugin_message_summary`` 的群消息记录新增 ``platform_user_id`` 列，
   保存 ``event.get_user_id()``（QQ 官方群里即 member_openid）。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b8e2f1a4c7d9"
down_revision: str | Sequence[str] | None = "398dc14b670d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_INFO_TABLE = "nonebot_plugin_larkuser_qq_group_info"
NEW_INFO_TABLE = "nonebot_plugin_qq_group_info"
OLD_MEMBER_TABLE = "nonebot_plugin_larkuser_qq_group_member"
NEW_MEMBER_TABLE = "nonebot_plugin_qq_group_member"

MESSAGE_TABLE = "nonebot_plugin_message_summary_groupmessage"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        statement = sa.text("SHOW TABLES LIKE :table_name")
    else:
        statement = sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name")
    return bool(bind.execute(statement, {"table_name": table_name}).fetchall())


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _rename_table(old_table: str, new_table: str) -> None:
    if _table_exists(old_table) and not _table_exists(new_table):
        op.rename_table(old_table, new_table)


def upgrade(name: str = "") -> None:
    if name:
        return

    _rename_table(OLD_INFO_TABLE, NEW_INFO_TABLE)
    _rename_table(OLD_MEMBER_TABLE, NEW_MEMBER_TABLE)

    if not _column_exists(MESSAGE_TABLE, "platform_user_id"):
        op.add_column(
            MESSAGE_TABLE,
            sa.Column("platform_user_id", sa.String(length=128), nullable=True),
        )


def downgrade(name: str = "") -> None:
    if name:
        return

    if _column_exists(MESSAGE_TABLE, "platform_user_id"):
        op.drop_column(MESSAGE_TABLE, "platform_user_id")

    _rename_table(NEW_INFO_TABLE, OLD_INFO_TABLE)
    _rename_table(NEW_MEMBER_TABLE, OLD_MEMBER_TABLE)
