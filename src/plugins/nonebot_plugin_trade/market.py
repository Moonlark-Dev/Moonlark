from __future__ import annotations

import math
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Literal, Optional

from sqlalchemy import select

if TYPE_CHECKING:
    from nonebot_plugin_larkuser import MoonlarkUser
    from nonebot_plugin_orm import AsyncSession

from .config import config
from .models import Candle, Holding, MarketState

# 中国标准时间；交易时间按 UTC+8 的本地时间解释
TZ = timezone(timedelta(hours=8))
TICK_MINUTES = 5
OPEN_MINUTE = 8 * 60
CLOSE_MINUTE = 24 * 60
LAST_TICK_MINUTE = CLOSE_MINUTE - TICK_MINUTES
TARGET_MIN_MINUTE = 11 * 60
TARGET_MAX_MINUTE = 20 * 60
PRICE_FLOOR = 0.01
LABEL_UP = "up"
LABEL_DOWN = "down"
LABEL_FLAT = "flat"
LABELS = (LABEL_UP, LABEL_DOWN, LABEL_FLAT)
# 段内进度对涨跌概率的最大偏移：进度 1 时 p_up = 0.95 / 0.05
MAX_BIAS = 0.45
# 布朗桥插值的采样点数：每两根 tick 之间补出的盘中路径
BRIDGE_STEPS = 16
# 隔夜跳空的最小幅度（相对前一交易日收盘价），保证开市时能看到缺口
GAP_MIN_RATIO = 0.005
_RANDOM_SCALE = 1_000_000_000
_BUY_SHARES_PATTERN = re.compile(r"\d+")
_SELL_SHARES_PATTERN = re.compile(r"\d+")


class TradeError(Exception):
    """交易失败，key 为语言文件中的错误键"""

    def __init__(self, key: str, *format_args: object) -> None:
        super().__init__(key)
        self.key = key
        self.format_args = format_args


@dataclass(frozen=True)
class AmountSpec:
    kind: Literal["shares", "percent", "all"]
    value: float = 0.0


@dataclass(frozen=True)
class TradeResult:
    side: Literal["buy", "sell"]
    shares: int
    price: float
    gross: float
    fee: float
    amount: float
    impact: float
    new_price: float
    shares_after: int
    frozen_after: int
    sellable_after: int
    daily_bought: int
    daily_sold: int
    balance_after: float
    capped_reason: Optional[Literal["daily", "float"]] = None


def now_local() -> datetime:
    """当前 UTC+8 本地时间（naive）"""
    return datetime.now(TZ).replace(tzinfo=None)


def trading_day(now: datetime) -> date:
    """交易日以 08:00 为分界：00:00~07:59 仍属于前一个交易日"""
    return (now - timedelta(hours=8)).date()


def is_trading_time(now: datetime) -> bool:
    minute = now.hour * 60 + now.minute
    return OPEN_MINUTE <= minute < CLOSE_MINUTE


def target_tick_time(now: datetime) -> datetime:
    """当前应补算到的最近一个 tick 时间"""
    if is_trading_time(now):
        minute = (now.hour * 60 + now.minute) // TICK_MINUTES * TICK_MINUTES
        return datetime.combine(now.date(), time(minute // 60, minute % 60))
    return datetime.combine(trading_day(now), time(23, 55))


def next_tick_time(tick: datetime) -> datetime:
    minute = tick.hour * 60 + tick.minute
    if minute < OPEN_MINUTE:
        return datetime.combine(tick.date(), time(8, 0))
    if minute >= LAST_TICK_MINUTE:
        return datetime.combine(tick.date() + timedelta(days=1), time(8, 0))
    return tick + timedelta(minutes=TICK_MINUTES)


def candle_slot(minute: int) -> Optional[int]:
    """tick 时间 -> 该 tick 刚收盘的 5 分钟 K 线下标；08:00 之前返回 None"""
    if minute < OPEN_MINUTE:
        return None
    return max(0, (minute - OPEN_MINUTE) // TICK_MINUTES - 1)


def trade_candle_slot(minute: int) -> Optional[int]:
    """成交时间 -> 当前正在形成的 5 分钟 K 线下标；08:00 之前返回 None"""
    if minute < OPEN_MINUTE:
        return None
    return (minute - OPEN_MINUTE) // TICK_MINUTES


def _rand_unit() -> float:
    """[0, 1) 均匀分布，底层使用 urandom"""
    return secrets.randbelow(_RANDOM_SCALE) / _RANDOM_SCALE


def _rand_float() -> float:
    """[0, 1) 均匀分布；测试通过打桩它控制 tick 的方向与幅度"""
    return _rand_unit()


def _rand_normal() -> float:
    """标准正态随机数（Box-Muller），用于布朗桥插值"""
    u1 = max(_rand_unit(), 1e-12)
    u2 = _rand_unit()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _random_gap_ratio() -> float:
    """隔夜跳空幅度：方向随机，绝对值落在 GAP_MIN_RATIO~trade_gap_sigma 之间"""
    cap = max(GAP_MIN_RATIO, config.trade_gap_sigma)
    magnitude = GAP_MIN_RATIO + _rand_float() * (cap - GAP_MIN_RATIO)
    return magnitude if _rand_float() >= 0.5 else -magnitude


def _brownian_bridge_extremes(start: float, end: float, volatility: float) -> tuple[float, float]:
    """在两个 tick 的价格之间用布朗桥补出盘中路径，返回 (最高价, 最低价)

    布朗桥的起点、终点分别固定为两根 tick 的价格，中间采样点按
    ``B(t) = start + (end - start) * t + Z * volatility * sqrt(t * (1 - t))`` 生成，
    这样即使开收盘价相同，K 线也会出现合理的上下影线。
    """
    high = max(start, end)
    low = min(start, end)
    spread = max(PRICE_FLOOR, end) * volatility
    if spread <= 0:
        return high, low
    for step in range(1, BRIDGE_STEPS):
        t = step / BRIDGE_STEPS
        deviation = max(-3.0, min(3.0, _rand_normal())) * spread * math.sqrt(t * (1.0 - t))
        point = max(PRICE_FLOOR, start + (end - start) * t + deviation)
        high = max(high, point)
        low = min(low, point)
    return high, low


def _random_target_minute() -> int:
    """11:00~20:00 之间随机一个分钟数（含两端）"""
    return TARGET_MIN_MINUTE + secrets.randbelow(TARGET_MAX_MINUTE - TARGET_MIN_MINUTE + 1)


def _random_label() -> str:
    return secrets.choice(LABELS)


def init_day(state: MarketState, day: date) -> None:
    """开市初始化：开盘价暂取前一交易日收盘价，并抽取当日内部行情参数"""
    state.prev_close = state.price
    state.day_open = state.price
    state.day = day
    state.target_minute = _random_target_minute()
    state.label1 = _random_label()
    state.label2 = _random_label()


def apply_open_gap(state: MarketState) -> None:
    """开市跳空：立即 tick 一次，从昨收直接跳到当日开盘价（不写 K 线，形成缺口）"""
    state.day_open = _round_price(state.price * (1 + _random_gap_ratio()))
    state.price = state.day_open


def segment_label_and_progress(state: MarketState, minute: int) -> tuple[str, float]:
    """返回当前分钟所在段落的标签与段内进度（0~1）"""
    target = state.target_minute
    if minute < target - 30:
        span = max(1, target - 30 - OPEN_MINUTE)
        return state.label1, min(1.0, max(0.0, (minute - OPEN_MINUTE) / span))
    if minute <= target + 30:
        return LABEL_FLAT, 0.5
    span = max(1, CLOSE_MINUTE - (target + 30))
    return state.label2, min(1.0, max(0.0, (minute - (target + 30)) / span))


def up_probability(label: str, progress: float) -> float:
    """标签 + 段内进度 -> 本次 tick 上涨概率"""
    if label == LABEL_UP:
        return 0.5 + MAX_BIAS * progress
    if label == LABEL_DOWN:
        return 0.5 - MAX_BIAS * progress
    return 0.5


def impact_rate(shares: int) -> float:
    """单笔买卖冲击，按总股本 10 万股计算，封顶 1%"""
    if shares <= 0:
        return 0.0
    total_shares = max(1, config.trade_total_shares)
    return min(config.trade_max_impact, shares / total_shares)


def _round_price(price: float) -> float:
    return round(max(PRICE_FLOOR, price), 6)


async def apply_tick(state: MarketState, tick: datetime, session: AsyncSession) -> None:
    """应用一次 tick：按段内概率决定方向，幅度不超过 sigma"""
    minute = tick.hour * 60 + tick.minute
    label, progress = segment_label_and_progress(state, minute)
    p_up = up_probability(label, progress)
    direction = 1 if _rand_float() < p_up else -1
    magnitude = _rand_float() * config.trade_sigma
    old_price = state.price
    new_price = _round_price(old_price * (1 + direction * magnitude))
    state.price = new_price

    slot = candle_slot(minute)
    if slot is None:
        return
    high, low = _brownian_bridge_extremes(old_price, new_price, config.trade_sigma * config.trade_bridge_vol)
    candle = await session.get(Candle, (tick.date(), slot))
    if candle is None:
        session.add(
            Candle(
                day=tick.date(),
                slot=slot,
                open=old_price,
                high=high,
                low=low,
                close=new_price,
                volume=0,
            ),
        )
        return
    candle.high = max(candle.high, high)
    candle.low = min(candle.low, low)
    candle.close = new_price


async def ensure_market(session: AsyncSession, now: Optional[datetime] = None) -> MarketState:
    """读取市场状态，并把上次访问以来的 tick 全部补算到当前时刻"""
    now = now or now_local()
    state = await session.get(MarketState, 1)
    if state is None:
        initial_price = max(PRICE_FLOOR, config.trade_initial_price)
        state = MarketState(
            id=1,
            price=initial_price,
            day_open=initial_price,
            prev_close=initial_price,
            target_minute=TARGET_MIN_MINUTE,
            label1=LABEL_FLAT,
            label2=LABEL_FLAT,
            float_shares=config.trade_total_shares,
            last_tick_at=None,
        )
        session.add(state)
        await session.flush()

    if state.last_tick_at is None:
        if is_trading_time(now):
            init_day(state, now.date())
            apply_open_gap(state)
            state.last_tick_at = datetime.combine(now.date(), time(8, 0))
        else:
            day = trading_day(now)
            state.day = day
            state.day_open = state.price
            state.prev_close = state.price
            state.target_minute = _random_target_minute()
            state.label1 = _random_label()
            state.label2 = _random_label()
            state.last_tick_at = datetime.combine(day, time(23, 55))

    target = target_tick_time(now)
    while state.last_tick_at < target:
        tick = next_tick_time(state.last_tick_at)
        if tick > target:
            break
        if tick.hour * 60 + tick.minute == OPEN_MINUTE:
            init_day(state, tick.date())
            apply_open_gap(state)
        else:
            await apply_tick(state, tick, session)
        state.last_tick_at = tick
    await session.flush()
    return state


async def get_holding(session: AsyncSession, user_id: str, day: date) -> Holding:
    """读取用户持仓，并按交易日懒重置 T+1 冻结与每日交易计数"""
    holding = await session.get(Holding, user_id)
    if holding is None:
        holding = Holding(
            user_id=user_id,
            shares=0,
            frozen_shares=0,
            cost_basis=0.0,
            last_active_day=day,
            daily_bought=0,
            daily_sold=0,
        )
        session.add(holding)
        return holding
    if holding.last_active_day != day:
        holding.frozen_shares = 0
        holding.daily_bought = 0
        holding.daily_sold = 0
        holding.last_active_day = day
    return holding


def parse_buy_amount(raw: str) -> AmountSpec:
    text = raw.strip()
    if not text:
        raise TradeError("error.invalid_buy_amount")
    if text.lower() == "all":
        return AmountSpec("all")
    if text.endswith("%"):
        try:
            percent = float(text[:-1]) / 100
        except ValueError as e:
            raise TradeError("error.invalid_buy_amount") from e
        if not math.isfinite(percent) or percent <= 0 or percent > 1:
            raise TradeError("error.percent_range")
        return AmountSpec("percent", percent)
    if "." in text:
        try:
            percent = float(text)
        except ValueError as e:
            raise TradeError("error.invalid_buy_amount") from e
        if not math.isfinite(percent) or percent <= 0 or percent > 1:
            raise TradeError("error.percent_range")
        return AmountSpec("percent", percent)
    if not _BUY_SHARES_PATTERN.fullmatch(text):
        raise TradeError("error.invalid_buy_amount")
    shares = int(text)
    if shares <= 0:
        raise TradeError("error.invalid_buy_amount")
    return AmountSpec("shares", float(shares))


def parse_sell_amount(raw: str) -> AmountSpec:
    text = raw.strip()
    if not text:
        raise TradeError("error.invalid_sell_amount")
    if text.lower() == "all":
        return AmountSpec("all")
    if not _SELL_SHARES_PATTERN.fullmatch(text):
        raise TradeError("error.invalid_sell_amount")
    shares = int(text)
    if shares <= 0:
        raise TradeError("error.invalid_sell_amount")
    return AmountSpec("shares", float(shares))


def _gross_fee_amount(shares: int, price: float, side: Literal["buy", "sell"]) -> tuple[float, float, float]:
    gross = round(shares * price, 2)
    fee = round(gross * config.trade_fee_rate, 2)
    if side == "buy":
        return gross, fee, round(gross + fee, 2)
    return gross, fee, round(max(0.0, gross - fee), 2)


async def update_candle_on_trade(
    session: AsyncSession,
    state: MarketState,
    now: datetime,
    old_price: float,
    new_price: float,
    shares: int,
) -> None:
    """成交后立即把冲击价写进当前 5 分钟 K 线"""
    if state.day is None:
        return
    slot = trade_candle_slot(now.hour * 60 + now.minute)
    if slot is None:
        return
    candle = await session.get(Candle, (state.day, slot))
    if candle is None:
        session.add(
            Candle(
                day=state.day,
                slot=slot,
                open=old_price,
                high=max(old_price, new_price),
                low=min(old_price, new_price),
                close=new_price,
                volume=shares,
            ),
        )
        return
    candle.high = max(candle.high, new_price)
    candle.low = min(candle.low, new_price)
    candle.close = new_price
    candle.volume += shares


async def execute_buy(
    session: AsyncSession,
    state: MarketState,
    user: MoonlarkUser,
    raw_amount: str,
    now: Optional[datetime] = None,
) -> TradeResult:
    now = now or now_local()
    if not is_trading_time(now):
        raise TradeError("error.not_trading")
    holding = await get_holding(session, user.user_id, trading_day(now))
    spec = parse_buy_amount(raw_amount)
    price = state.price
    balance = user.get_vimcoin()
    daily_remaining = config.trade_daily_limit - holding.daily_bought
    if daily_remaining <= 0:
        raise TradeError("error.daily_buy_limit", 0)
    if state.float_shares <= 0:
        raise TradeError("error.market_empty")

    if spec.kind == "shares":
        shares = int(spec.value)
        if shares > daily_remaining:
            raise TradeError("error.daily_buy_limit", daily_remaining)
        if shares > state.float_shares:
            raise TradeError("error.not_enough_float", state.float_shares)
        gross, fee, amount = _gross_fee_amount(shares, price, "buy")
        if amount > balance:
            raise TradeError("error.not_enough_vimcoin", amount, balance)
        capped_reason: Optional[Literal["daily", "float"]] = None
    else:
        budget = balance if spec.kind == "all" else balance * spec.value
        desired = math.floor(budget / (price * (1 + config.trade_fee_rate))) if price > 0 else 0
        capped_reason = None
        if desired > daily_remaining:
            capped_reason = "daily"
        elif desired > state.float_shares:
            capped_reason = "float"
        shares = min(desired, daily_remaining, state.float_shares)
        while shares > 0:
            gross, fee, amount = _gross_fee_amount(shares, price, "buy")
            if amount <= balance:
                break
            shares -= 1
        if shares <= 0:
            raise TradeError("error.amount_too_small")
        gross, fee, amount = _gross_fee_amount(shares, price, "buy")

    if shares <= 0:
        raise TradeError("error.amount_too_small")
    if not await user.use_vimcoin(amount):
        raise TradeError("error.not_enough_vimcoin", amount, balance)

    holding.shares += shares
    holding.frozen_shares += shares
    holding.cost_basis = round(holding.cost_basis + amount, 2)
    holding.daily_bought += shares
    state.float_shares -= shares

    impact = impact_rate(shares)
    old_price = state.price
    new_price = _round_price(old_price * (1 + impact))
    state.price = new_price
    await update_candle_on_trade(session, state, now, old_price, new_price, shares)
    return TradeResult(
        side="buy",
        shares=shares,
        price=price,
        gross=gross,
        fee=fee,
        amount=amount,
        impact=impact,
        new_price=new_price,
        shares_after=holding.shares,
        frozen_after=holding.frozen_shares,
        sellable_after=holding.shares - holding.frozen_shares,
        daily_bought=holding.daily_bought,
        daily_sold=holding.daily_sold,
        balance_after=user.get_vimcoin(),
        capped_reason=capped_reason,
    )


async def execute_sell(
    session: AsyncSession,
    state: MarketState,
    user: MoonlarkUser,
    raw_amount: str,
    now: Optional[datetime] = None,
) -> TradeResult:
    now = now or now_local()
    if not is_trading_time(now):
        raise TradeError("error.not_trading")
    holding = await get_holding(session, user.user_id, trading_day(now))
    spec = parse_sell_amount(raw_amount)
    sellable = holding.shares - holding.frozen_shares
    if sellable <= 0:
        raise TradeError("error.no_sellable")
    daily_remaining = config.trade_daily_limit - holding.daily_sold
    if daily_remaining <= 0:
        raise TradeError("error.daily_sell_limit", 0)

    capped_reason: Optional[Literal["daily", "float"]] = None
    if spec.kind == "all":
        shares = min(sellable, daily_remaining)
        if shares < sellable:
            capped_reason = "daily"
    else:
        shares = int(spec.value)
        if shares > sellable:
            raise TradeError("error.not_enough_shares", sellable)
        if shares > daily_remaining:
            raise TradeError("error.daily_sell_limit", daily_remaining)
    if shares <= 0:
        raise TradeError("error.no_sellable")

    price = state.price
    gross, fee, amount = _gross_fee_amount(shares, price, "sell")
    await user.add_vimcoin(amount)

    average_cost = holding.cost_basis / holding.shares if holding.shares > 0 else 0.0
    holding.cost_basis = round(max(0.0, holding.cost_basis - average_cost * shares), 2)
    holding.shares -= shares
    if holding.shares == 0:
        holding.cost_basis = 0.0
    holding.daily_sold += shares
    state.float_shares += shares

    impact = impact_rate(shares)
    old_price = state.price
    new_price = _round_price(old_price * (1 - impact))
    state.price = new_price
    await update_candle_on_trade(session, state, now, old_price, new_price, shares)
    return TradeResult(
        side="sell",
        shares=shares,
        price=price,
        gross=gross,
        fee=fee,
        amount=amount,
        impact=impact,
        new_price=new_price,
        shares_after=holding.shares,
        frozen_after=holding.frozen_shares,
        sellable_after=holding.shares - holding.frozen_shares,
        daily_bought=holding.daily_bought,
        daily_sold=holding.daily_sold,
        balance_after=user.get_vimcoin(),
        capped_reason=capped_reason,
    )


async def load_recent_candles(session: AsyncSession, limit: int) -> list[Candle]:
    """按时间升序读取最近 limit 根已收盘的 5 分钟 K 线（可跨交易日）

    K 线图固定展示最近若干根蜡烛，当日蜡烛不足时自动补上此前交易日的数据。
    """
    if limit <= 0:
        return []
    candles = list(
        await session.scalars(
            select(Candle).order_by(Candle.day.desc(), Candle.slot.desc()).limit(limit),
        ),
    )
    candles.reverse()
    return candles
