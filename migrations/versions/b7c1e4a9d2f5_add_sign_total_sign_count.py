"""add sign total sign count

`nonebot_plugin_sign_signdata` 新增 `total_sign_count`（累计签到次数）：新用户福利
按「使用签到的次数」判定（前 3 次每次额外 100vi），不能用会因断签重置的
`sign_days`，也不能用注册时间。此前注册但从未签到的用户该列默认 0，同样算新用户。

存量数据回填：`sign_days > 0` 说明用户至少签到过一次（该列只会被重置成 1，不会被清空），
这些用户不算新用户，直接记为 3（再签一次即超过 3 次，不会发放福利）。从未签过的是默认 0。

迁移 ID: b7c1e4a9d2f5
父迁移: d3e5f7a9b1c2
创建时间: 2026-11-26 18:45:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "b7c1e4a9d2f5"
down_revision: str | Sequence[str] | None = "d3e5f7a9b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "nonebot_plugin_sign_signdata"
COLUMNS = {
    "total_sign_count": sa.Column("total_sign_count", sa.Integer(), nullable=False, server_default="0"),
}


def upgrade(name: str = "") -> None:
    if name:
        return
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns(TABLE)]
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for column_name, column in COLUMNS.items():
            if column_name not in columns:
                batch_op.add_column(column)
    # 存量用户里签到过一次及以上的不算新用户，避免上线后老用户白拿 3 次福利
    op.execute(
        sa.text("UPDATE nonebot_plugin_sign_signdata SET total_sign_count = :count WHERE sign_days > 0").bindparams(
            count=3,
        ),
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for column_name in COLUMNS:
            batch_op.drop_column(column_name)
