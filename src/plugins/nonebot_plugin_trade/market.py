from __future__ import annotations

import json
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
PRICE_FLOOR = 0.01
LABEL_UP = "up"
LABEL_DOWN = "down"
LABEL_FLAT = "flat"
LABELS = (LABEL_UP, LABEL_DOWN, LABEL_FLAT)
# 段内进度对涨跌概率的最大偏移：进度 1 时 p_up = 0.95 / 0.05
MAX_BIAS = 0.45
# 布朗桥插值的采样点数：每两根 tick 之间补出的盘中路径
BRIDGE_STEPS = 16
# 每天开盘前循环抽取行情段时，每段持续时间（tick 数）的下限与上限
MIN_SEGMENT_TICKS = 3
MAX_SEGMENT_TICKS = 15
# 交易时段 08:00–24:00 的 tick 总数；08:00 的开市跳空 tick 不占用当日分配
DAY_TICKS = (CLOSE_MINUTE - OPEN_MINUTE) // TICK_MINUTES
INTRADAY_TICKS = DAY_TICKS - 1
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
class Segment:
    """当日行情序列的一段：标签与它持续的 tick 数"""

    label: str
    ticks: int


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


def _random_label() -> str:
    return secrets.choice(LABELS)


def allocate_segments(tick_count: int = INTRADAY_TICKS) -> list[Segment]:
    """循环抽取标签与持续时间，直到把 tick_count 个 tick 完整分配

    每轮抽一个标签和一个 MIN_SEGMENT_TICKS~MAX_SEGMENT_TICKS 的持续时间；
    剩下的 tick 不足以再抽一段时直接并进最后一段，保证每段都不短于下限。
    """
    segments: list[Segment] = []
    remaining = tick_count
    while remaining > 0:
        if remaining <= MAX_SEGMENT_TICKS:
            ticks = remaining
        else:
            span = MAX_SEGMENT_TICKS - MIN_SEGMENT_TICKS + 1
            ticks = min(MAX_SEGMENT_TICKS, MIN_SEGMENT_TICKS + int(_rand_float() * span))
            if remaining - ticks < MIN_SEGMENT_TICKS:
                ticks = remaining - MIN_SEGMENT_TICKS
        segments.append(Segment(_random_label(), ticks))
        remaining -= ticks
    return segments


def encode_segments(segments: list[Segment]) -> str:
    """把当日行情序列序列化成 JSON，存进 MarketState.segments"""
    return json.dumps([{"label": segment.label, "ticks": segment.ticks} for segment in segments])


def decode_segments(raw: Optional[str]) -> list[Segment]:
    """解析行情序列；空值或损坏的 JSON 一律视为尚未分配"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    segments: list[Segment] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        ticks = item.get("ticks")
        if label in LABELS and isinstance(ticks, int) and ticks > 0:
            segments.append(Segment(label, ticks))
    return segments


def get_segments(state: MarketState) -> list[Segment]:
    """读取当日行情序列"""
    return decode_segments(state.segments)


def _round_price(price: float) -> float:
    return round(max(PRICE_FLOOR, price), 6)


def up_probability(label: str, progress: float) -> float:
    """标签 + 段内进度 -> 本次 tick 上涨概率"""
    if label == LABEL_UP:
        return 0.5 + MAX_BIAS * progress
    if label == LABEL_DOWN:
        return 0.5 - MAX_BIAS * progress
    return 0.5


def _tick_price(old_price: float, label: str, progress: float) -> float:
    """按标签与段内进度走一个 tick：方向按概率抽，幅度不超过 trade_sigma"""
    p_up = up_probability(label, progress)
    direction = 1 if _rand_float() < p_up else -1
    magnitude = _rand_float() * config.trade_sigma
    return _round_price(old_price * (1 + direction * magnitude))


def init_day(state: MarketState, day: date) -> None:
    """开市初始化：开盘价暂取前一交易日收盘价

    当天全天的行情序列在处理 08:00 的 tick 时一次性抽好，先于当日任何一个 tick。
    """
    state.prev_close = state.price
    state.day_open = state.price
    state.day = day
    state.segments = encode_segments(allocate_segments())


def last_segment_label(state: MarketState) -> str:
    """当日行情序列最后一个标签；序列还没分配时按持平处理"""
    segments = get_segments(state)
    return segments[-1].label if segments else LABEL_FLAT


def apply_open_gap(state: MarketState, last_label: str) -> None:
    """开市跳空：按前一交易日最后一个标签再走一个 tick，形成不写 K 线的缺口"""
    state.day_open = _tick_price(state.price, last_label, 1.0)
    state.price = state.day_open


def segment_label_and_progress(state: MarketState, minute: int) -> tuple[str, float]:
    """返回当前 tick 所属段落的标签与段内进度（0~1）

    08:00 的开市跳空 tick 由前一交易日最后一个标签决定，不占用当日分配，
    当日分配的第一个 tick 是 08:05。
    """
    segments = get_segments(state)
    if not segments:
        return LABEL_FLAT, 0.5
    total_ticks = sum(segment.ticks for segment in segments)
    position = max(0, min((minute - OPEN_MINUTE) // TICK_MINUTES - 1, total_ticks - 1))
    start = 0
    for segment in segments:
        if position < start + segment.ticks:
            progress = (position - start) / max(1, segment.ticks - 1)
            return segment.label, progress
        start += segment.ticks
    return segments[-1].label, 1.0


def impact_rate(shares: int) -> float:
    """单笔买卖冲击，按总股本 10 万股计算，封顶 1%"""
    if shares <= 0:
        return 0.0
    total_shares = max(1, config.trade_total_shares)
    return min(config.trade_max_impact, shares / total_shares)


async def apply_tick(state: MarketState, tick: datetime, session: AsyncSession) -> None:
    """应用一次 tick：按段内概率决定方向，幅度不超过 sigma"""
    minute = tick.hour * 60 + tick.minute
    label, progress = segment_label_and_progress(state, minute)
    old_price = state.price
    new_price = _tick_price(old_price, label, progress)
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
            segments=None,
            float_shares=config.trade_total_shares,
            last_tick_at=None,
        )
        session.add(state)
        await session.flush()

    if state.last_tick_at is None:
        if is_trading_time(now):
            # 冷启动没有历史收盘价，不制造隔夜跳空，只把交易日初始化到当天
            init_day(state, now.date())
            state.last_tick_at = datetime.combine(now.date(), time(8, 0))
        else:
            day = trading_day(now)
            init_day(state, day)
            state.last_tick_at = datetime.combine(day, time(23, 55))
    elif not get_segments(state):
        # 从旧版本升级上来：当天还没有行情序列，先补齐再继续补算 tick
        state.segments = encode_segments(allocate_segments())

    target = target_tick_time(now)
    while state.last_tick_at < target:
        tick = next_tick_time(state.last_tick_at)
        if tick > target:
            break
        if tick.hour * 60 + tick.minute == OPEN_MINUTE:
            # 隔夜跳空按前一交易日最后一个标签再走一个 tick，所以要在换日前取
            last_label = last_segment_label(state)
            init_day(state, tick.date())
            apply_open_gap(state, last_label)
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
    """按时间升序读取最近 limit 根 5 分钟 K 线（可跨交易日，最后一根可能是正在形成的）

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
