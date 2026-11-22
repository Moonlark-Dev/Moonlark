"""trade candlebridge state

`nonebot_plugin_trade_marketstate` 将旧的分段行情列 `segments` 替换为
CandleBridge 随机过程状态列 `engine_state`（JSON 文本）。

迁移 ID: f4a9d1e2b8c6
父迁移: c8d5e3b02f74
创建时间: 2026-11-22 01:12:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "f4a9d1e2b8c6"
down_revision: str | Sequence[str] | None = "c8d5e3b02f74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_trade_marketstate", schema=None) as batch_op:
        batch_op.add_column(sa.Column("engine_state", sa.Text(), nullable=True))
        batch_op.drop_column("segments")


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table("nonebot_plugin_trade_marketstate", schema=None) as batch_op:
        batch_op.add_column(sa.Column("segments", sa.Text(), nullable=True))
        batch_op.drop_column("engine_state")
