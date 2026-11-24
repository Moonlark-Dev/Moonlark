"""add trade ranking totals

`nonebot_plugin_trade_holding` 新增累计买入支出 `total_bought` 与累计卖出到账
`total_sold`，用于 `/trade rank` 的收益排行榜。

老数据没有历史成交记录，按当前持仓成本回填 `total_bought`：对仍持股的用户，
收益率恰好等于其浮动盈亏率；已经清仓的用户无法还原历史，暂不参与排行。

迁移 ID: d3e5f7a9b1c2
父迁移: f4a9d1e2b8c6
创建时间: 2026-11-23 15:55:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d3e5f7a9b1c2"
down_revision: str | Sequence[str] | None = "f4a9d1e2b8c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "nonebot_plugin_trade_holding"
COLUMNS = {
    "total_bought": sa.Column("total_bought", sa.Float(), nullable=False, server_default="0"),
    "total_sold": sa.Column("total_sold", sa.Float(), nullable=False, server_default="0"),
}


def upgrade(name: str = "") -> None:
    if name:
        return
    columns = [column["name"] for column in inspect(op.get_bind()).get_columns(TABLE)]
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for column_name, column in COLUMNS.items():
            if column_name not in columns:
                batch_op.add_column(column)
    if "total_bought" not in columns:
        holding = sa.table(TABLE, sa.column("cost_basis"), sa.column("total_bought"))
        op.execute(
            holding.update()
            .where(holding.c.total_bought == 0)
            .where(holding.c.cost_basis > 0)
            .values(total_bought=holding.c.cost_basis),
        )


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for column_name in COLUMNS:
            batch_op.drop_column(column_name)
