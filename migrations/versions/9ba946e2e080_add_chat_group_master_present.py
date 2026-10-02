"""merge heads 并给 chat_group 添加 master_present

迁移 ID: 9ba946e2e080
父迁移: 9f6eedd5686c, b7e1f4a9c2d3
创建时间: 2026-10-02 19:22:00.000000

main 上同时存在 9f6eedd5686c（市场插件）与 b7e1f4a9c2d3（Buff 效果系统）两个 head，
本迁移将它们合并为一个 head，同时为群聊记录添加「主人是否出现过」标记：

- nonebot_plugin_chat_chatgroup.master_present：主人（CHAT_MASTER_USER_ID）是否在
  本群的 Message Summary 记录中出现过。会话元数据据此生成「XiaoDeng3386 是否在
  当前会话」指示；该列为 False 时仍会回查消息记录，一旦更新为 True 便只增不减，
  除非手动修改数据库。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "9ba946e2e080"
down_revision: str | Sequence[str] | None = ("9f6eedd5686c", "b7e1f4a9c2d3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_chat_chatgroup"
COLUMN_NAME = "master_present"


def upgrade(name: str = "") -> None:
    if name:
        return
    inspector = inspect(op.get_bind())
    columns = [column["name"] for column in inspector.get_columns(TABLE_NAME)]
    if COLUMN_NAME not in columns:
        with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
            batch_op.add_column(sa.Column(COLUMN_NAME, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_column(COLUMN_NAME)
