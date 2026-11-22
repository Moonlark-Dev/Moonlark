from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Literal, Optional

from sqlalchemy import select

if TYPE_CHECKING:
    from nonebot_plugin_larkuser import MoonlarkUser
    from nonebot_plugin_orm import AsyncSession

from .candlebridge import ModelParameters, PathState, simulate_bar
from .config import config
from .models import Candle, Holding, MarketState

# 中国标准时间；交易时间按 UTC+8 的本地时间解释
TZ = timezone(timedelta(hours=8))
TICK_MINUTES = 5
OPEN_MINUTE = 8 * 60
CLOSE_MINUTE = 24 * 60
LAST_TICK_MINUTE = CLOSE_MINUTE - TICK_MINUTES
PRICE_FLOOR = 0.01
PRICE_DECIMALS = 6
# 交易时段 08:00–24:00 的 tick 总数；08:00 为开市跳空 tick
DAY_TICKS = (CLOSE_MINUTE - OPEN_MINUTE) // TICK_MINUTES
INTRADAY_TICKS = DAY_TICKS - 1
# 单个交易日最多落库的 5 分钟 K 线根数；批量读取日 K 时据此估算查询上限
MAX_CANDLES_PER_DAY = DAY_TICKS
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


@dataclass(frozen=True)
class DailyCandle:
    """由当日实际落库的 5 分钟 K 线聚合出的日 K 线"""

    day: date
    open: float
    high: float
    low: float
    close: float
    volume: int


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


def build_model_parameters() -> ModelParameters:
    """根据当前插件配置构建 CandleBridge 模型参数（连续市场模式关闭终点锁定）"""
    return ModelParameters(
        fine_seconds=config.trade_fine_seconds,
        df=config.trade_df,
        decay=config.trade_decay,
        base_volatility=config.trade_base_volatility,
        jump_probability=config.trade_jump_probability,
        jump_minimum=config.trade_jump_minimum,
        jump_maximum=config.trade_jump_maximum,
        shock=config.trade_shock,
        low_multiplier=config.trade_low_multiplier,
        high_multiplier=config.trade_high_multiplier,
        trend_multiplier=config.trade_trend_multiplier,
        state_minimum=config.trade_state_minimum,
        state_maximum=config.trade_state_maximum,
        trend_strength=config.trade_trend_strength,
        intensity=config.trade_intensity,
        lock_target=False,
    )


def encode_engine_state(engine: PathState) -> str:
    """把 CandleBridge 随机过程状态序列化为 JSON，存进 MarketState.engine_state"""
    return json.dumps(engine.to_dict(), separators=(",", ":"))


def decode_engine_state(raw: Optional[str]) -> Optional[PathState]:
    """解析随机过程状态；空值、损坏 JSON 或非法字段一律视为尚未初始化"""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return PathState.from_dict(data)


def get_engine_state(state: MarketState) -> Optional[PathState]:
    """读取当前市场保存的 CandleBridge 状态"""
    return decode_engine_state(state.engine_state)


def ensure_engine_state(state: MarketState, model: Optional[ModelParameters] = None) -> PathState:
    """读取或按随机种子初始化 CandleBridge 状态，并写回 ``state.engine_state``"""
    engine = get_engine_state(state)
    if engine is not None:
        return engine
    engine = PathState.create(model or build_model_parameters())
    state.engine_state = encode_engine_state(engine)
    return engine


def _round_price(price: float) -> float:
    return round(max(PRICE_FLOOR, price), PRICE_DECIMALS)


def init_day(state: MarketState, day: date) -> None:
    """开市初始化：开盘价暂取前一交易日收盘价，并保留 CandleBridge 状态跨日延续"""
    state.prev_close = state.price
    state.day_open = state.price
    state.day = day
    ensure_engine_state(state)


def apply_open_gap(state: MarketState) -> None:
    """开市跳空：沿用前一交易日尾盘的 CandleBridge 状态演进隔夜区间，不写 K 线"""
    gap_minutes = config.trade_open_gap_minutes
    if gap_minutes <= 0:
        return
    model = build_model_parameters()
    engine = ensure_engine_state(state, model)
    bar = simulate_bar(
        engine,
        state.price,
        gap_minutes * 60,
        model,
        price_floor=PRICE_FLOOR,
        price_decimals=PRICE_DECIMALS,
    )
    state.engine_state = encode_engine_state(engine)
    state.day_open = bar.close
    state.price = bar.close


def impact_rate(shares: int) -> float:
    """单笔买卖冲击，按总股本 10 万股计算，封顶 1%"""
    if shares <= 0:
        return 0.0
    total_shares = max(1, config.trade_total_shares)
    return min(config.trade_max_impact, shares / total_shares)


async def apply_tick(state: MarketState, tick: datetime, session: AsyncSession) -> None:
    """应用一次 5 分钟 tick：按 CandleBridge 细步随机路径生成该根 K 线的 OHLC"""
    minute = tick.hour * 60 + tick.minute
    model = build_model_parameters()
    engine = ensure_engine_state(state, model)
    bar = simulate_bar(
        engine,
        state.price,
        TICK_MINUTES * 60,
        model,
        price_floor=PRICE_FLOOR,
        price_decimals=PRICE_DECIMALS,
    )
    state.engine_state = encode_engine_state(engine)
    state.price = bar.close

    slot = candle_slot(minute)
    if slot is None:
        return
    candle = await session.get(Candle, (tick.date(), slot))
    if candle is None:
        session.add(
            Candle(
                day=tick.date(),
                slot=slot,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=0,
            ),
        )
        return
    candle.high = max(candle.high, bar.high)
    candle.low = min(candle.low, bar.low)
    candle.close = bar.close


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
            engine_state=None,
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
    elif get_engine_state(state) is None:
        # 从旧版本升级上来：还没有 CandleBridge 状态，先补齐再继续补算 tick
        ensure_engine_state(state)

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


async def load_daily_candles(session: AsyncSession, limit: int) -> list[DailyCandle]:
    """按日期升序读取最近 limit 个交易日的日 K 线

    日 K 线完全由该交易日已落库的 5 分钟 K 线聚合：开盘价取首根、收盘价取末根，
    影线直接取当日全部 5 分钟 K 线的最高/最低价（含玩家买卖冲击写入的极值），
    不额外用随机模型生成日线影线。

    为了在一条查询里取够 limit 个完整交易日，按 ``limit * MAX_CANDLES_PER_DAY``
    行倒序取；多取的、被截断的旧交易日会被自然丢弃。
    """
    if limit <= 0:
        return []
    candles = list(
        await session.scalars(
            select(Candle).order_by(Candle.day.desc(), Candle.slot.desc()).limit(limit * MAX_CANDLES_PER_DAY),
        ),
    )
    grouped: dict[date, list[Candle]] = {}
    for candle in reversed(candles):
        grouped.setdefault(candle.day, []).append(candle)

    daily: list[DailyCandle] = []
    for day in sorted(grouped)[-limit:]:
        day_candles = grouped[day]
        daily.append(
            DailyCandle(
                day=day,
                open=day_candles[0].open,
                high=max(candle.high for candle in day_candles),
                low=min(candle.low for candle in day_candles),
                close=day_candles[-1].close,
                volume=sum(candle.volume or 0 for candle in day_candles),
            ),
        )
    return daily
