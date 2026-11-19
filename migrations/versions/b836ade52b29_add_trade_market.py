"""add trade market

迁移 ID: b836ade52b29
父迁移: b3c8f1d2e4a6
创建时间: 2026-11-19 14:44:14.554838

模拟股票市场：`nonebot_plugin_trade_marketstate` 保存全局行情状态，
`nonebot_plugin_trade_candle` 保存 5 分钟 K 线，
`nonebot_plugin_trade_holding` 保存用户持仓、T+1 冻结与每日交易计数。

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b836ade52b29"
down_revision: str | Sequence[str] | None = "b3c8f1d2e4a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_trade_candle",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("day", "slot", name=op.f("pk_nonebot_plugin_trade_candle")),
        info={"bind_key": "nonebot_plugin_trade"},
    )
    op.create_table(
        "nonebot_plugin_trade_holding",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("frozen_shares", sa.Integer(), nullable=False),
        sa.Column("cost_basis", sa.Float(), nullable=False),
        sa.Column("last_active_day", sa.Date(), nullable=True),
        sa.Column("daily_bought", sa.Integer(), nullable=False),
        sa.Column("daily_sold", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_nonebot_plugin_trade_holding")),
        info={"bind_key": "nonebot_plugin_trade"},
    )
    op.create_table(
        "nonebot_plugin_trade_marketstate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("day", sa.Date(), nullable=True),
        sa.Column("day_open", sa.Float(), nullable=False),
        sa.Column("prev_close", sa.Float(), nullable=False),
        sa.Column("target_minute", sa.Integer(), nullable=False),
        sa.Column("label1", sa.String(length=8), nullable=False),
        sa.Column("label2", sa.String(length=8), nullable=False),
        sa.Column("float_shares", sa.Integer(), nullable=False),
        sa.Column("last_tick_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nonebot_plugin_trade_marketstate")),
        info={"bind_key": "nonebot_plugin_trade"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_trade_marketstate")
    op.drop_table("nonebot_plugin_trade_holding")
    op.drop_table("nonebot_plugin_trade_candle")
