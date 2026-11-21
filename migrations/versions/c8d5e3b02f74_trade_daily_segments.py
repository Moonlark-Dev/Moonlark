"""trade daily segments

`nonebot_plugin_trade_marketstate` 不再保存两段行情标签（label1 / label2）和目标时间
（target_minute），改为保存每天开盘前抽好的当日行情序列 segments（JSON 文本）。

迁移 ID: c8d5e3b02f74
父迁移: 3f9a2c7d5e1b
创建时间: 2026-11-20 23:31:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d5e3b02f74"
down_revision: str | Sequence[str] | None = "3f9a2c7d5e1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_trade_marketstate", schema=None) as batch_op:
        batch_op.add_column(sa.Column("segments", sa.Text(), nullable=True))
        batch_op.drop_column("label1")
        batch_op.drop_column("label2")
        batch_op.drop_column("target_minute")


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_trade_marketstate", schema=None) as batch_op:
        batch_op.add_column(sa.Column("label1", sa.String(length=8), nullable=False, server_default="flat"))
        batch_op.add_column(sa.Column("label2", sa.String(length=8), nullable=False, server_default="flat"))
        batch_op.add_column(sa.Column("target_minute", sa.Integer(), nullable=False, server_default="0"))
        batch_op.drop_column("segments")
