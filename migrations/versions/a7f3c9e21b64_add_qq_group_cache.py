"""add qq group info and member cache tables

迁移 ID: a7f3c9e21b64
父迁移: 9f4e8c2a61b3d5f7
创建时间: 2026-09-11 11:20:00.000000

为 larkuser 插件新增 QQ 官方 Bot 群聊信息与群成员列表缓存表：
- nonebot_plugin_larkuser_qq_group_info：群基本信息与同步状态；
- nonebot_plugin_larkuser_qq_group_member：群成员列表缓存。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a7f3c9e21b64"
down_revision: str | Sequence[str] | None = "9f4e8c2a61b3d5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INFO_TABLE = "nonebot_plugin_larkuser_qq_group_info"
MEMBER_TABLE = "nonebot_plugin_larkuser_qq_group_member"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        statement = sa.text("SHOW TABLES LIKE :table_name")
    else:
        statement = sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name")
    return bool(bind.execute(statement, {"table_name": table_name}).fetchall())


def upgrade(name: str = "") -> None:
    if name:
        return

    if not _table_exists(INFO_TABLE):
        op.create_table(
            INFO_TABLE,
            sa.Column("group_openid", sa.String(length=128), nullable=False),
            sa.Column("bot_id", sa.String(length=64), nullable=False),
            sa.Column("group_name", sa.String(length=256), nullable=False),
            sa.Column("description", sa.String(length=512), nullable=False),
            sa.Column("member_count", sa.Integer(), nullable=False),
            sa.Column("info_updated_at", sa.DateTime(), nullable=True),
            sa.Column("members_synced_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.String(length=512), nullable=False),
            sa.PrimaryKeyConstraint("group_openid", name=op.f(f"pk_{INFO_TABLE}")),
            info={"bind_key": "nonebot_plugin_larkuser"},
        )

    if not _table_exists(MEMBER_TABLE):
        op.create_table(
            MEMBER_TABLE,
            sa.Column("group_openid", sa.String(length=128), nullable=False),
            sa.Column("member_openid", sa.String(length=128), nullable=False),
            sa.Column("nickname", sa.String(length=256), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("is_bot", sa.Boolean(), nullable=False),
            sa.Column("joined_at", sa.DateTime(), nullable=True),
            sa.Column("union_openid", sa.String(length=128), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("group_openid", "member_openid", name=op.f(f"pk_{MEMBER_TABLE}")),
            info={"bind_key": "nonebot_plugin_larkuser"},
        )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table(MEMBER_TABLE)
    op.drop_table(INFO_TABLE)
