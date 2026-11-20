from datetime import date, datetime
from typing import Optional

from nonebot_plugin_orm import Model
from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class MarketState(Model):
    """全局市场状态（单行，id 固定为 1）"""

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    # 最新成交价 / tick 价
    price: Mapped[float] = mapped_column(Float())
    # 当前交易日（以 08:00 为分界）
    day: Mapped[Optional[date]] = mapped_column(Date(), nullable=True)
    # 当日开盘价（开市跳空后的价格，可能不等于前一交易日收盘价）
    day_open: Mapped[float] = mapped_column(Float(), default=0.0)
    # 前一交易日收盘价
    prev_close: Mapped[float] = mapped_column(Float(), default=0.0)
    # 当日行情序列，开盘前一次性抽好，JSON 数组：[{"label": "up", "ticks": 5}, ...]
    segments: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    # 市场当前持有的流通股
    float_shares: Mapped[int] = mapped_column(Integer(), default=0)
    # 最近一次已处理的 tick 时间
    last_tick_at: Mapped[Optional[datetime]] = mapped_column(DateTime(), nullable=True)


class Candle(Model):
    """5 分钟 K 线"""

    day: Mapped[date] = mapped_column(Date(), primary_key=True)
    slot: Mapped[int] = mapped_column(Integer(), primary_key=True)
    open: Mapped[float] = mapped_column(Float())
    high: Mapped[float] = mapped_column(Float())
    low: Mapped[float] = mapped_column(Float())
    close: Mapped[float] = mapped_column(Float())
    volume: Mapped[int] = mapped_column(Integer(), default=0)


class Holding(Model):
    """用户持仓"""

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    shares: Mapped[int] = mapped_column(Integer(), default=0)
    # 当日买入、尚未解冻的股数（T+1）
    frozen_shares: Mapped[int] = mapped_column(Integer(), default=0)
    # 持仓成本（含买入手续费）
    cost_basis: Mapped[float] = mapped_column(Float(), default=0.0)
    # 最近一次结算的交易日，用于懒重置 T+1 与每日限额
    last_active_day: Mapped[Optional[date]] = mapped_column(Date(), nullable=True)
    daily_bought: Mapped[int] = mapped_column(Integer(), default=0)
    daily_sold: Mapped[int] = mapped_column(Integer(), default=0)
