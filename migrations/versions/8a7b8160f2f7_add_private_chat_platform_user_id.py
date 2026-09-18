"""记录私聊会话使用的适配器与适配器原始 user_id

迁移 ID: 8a7b8160f2f7
父迁移: b7d21f4c9a05
创建时间: 2026-09-17 16:00:44.658020

为 PrivateChatSession 新增两个字段：
- adapter_name：记录私聊时的适配器名称（如 OneBot V11、QQ）；
- platform_user_id：适配器原始 user_id（如 QQ 官方 openid）。

主动私聊发送时按这两个字段构造 Target：QQ 官方适配器发送 C2C 消息需要 openid，
而 user_id 可能是自动绑定后的主账号（QQ 号）。历史记录两个字段为空，发送时回退到 user_id。

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "8a7b8160f2f7"
down_revision: str | Sequence[str] | None = "b7d21f4c9a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_privatechatsession"


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.add_column(sa.Column("adapter_name", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("platform_user_id", sa.String(length=128), nullable=True))


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_column("platform_user_id")
        batch_op.drop_column("adapter_name")
