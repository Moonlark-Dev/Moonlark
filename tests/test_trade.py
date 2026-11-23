from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

TRADE_DAY = date(2026, 11, 19)


class FakeSession:
    """只实现行情/交易测试用到的最小 AsyncSession 接口"""

    def __init__(self) -> None:
        self.objects = {}

    async def get(self, model, key):
        return self.objects.get((model, key))

    def add(self, obj) -> None:
        from nonebot_plugin_trade.models import Candle, Holding, MarketState

        if isinstance(obj, Candle):
            self.objects[(Candle, (obj.day, obj.slot))] = obj
        elif isinstance(obj, Holding):
            self.objects[(Holding, obj.user_id)] = obj
        elif isinstance(obj, MarketState):
            self.objects[(MarketState, obj.id)] = obj

    async def flush(self) -> None:
        return None

    async def scalars(self, _statement):
        """load_recent_candles 的替身：按 (day, slot) 倒序返回全部 K 线（忽略 limit）"""
        from nonebot_plugin_trade.models import Candle

        candles = [obj for (model, _key), obj in self.objects.items() if model is Candle]
        return sorted(candles, key=lambda candle: (candle.day, candle.slot), reverse=True)


class FakeUser:
    user_id = "10001"

    def __init__(self, vimcoin: float = 0.0) -> None:
        self.vimcoin = float(vimcoin)

    def get_vimcoin(self) -> float:
        return self.vimcoin

    async def use_vimcoin(self, amount: float) -> bool:
        if self.vimcoin < amount:
            return False
        self.vimcoin -= amount
        return True

    async def add_vimcoin(self, amount: float) -> None:
        self.vimcoin += amount


def make_engine_state(seed: int = 20261007, **overrides: object) -> str:
    """构建并序列化一个确定性的 CandleBridge PathState，存进 MarketState.engine_state"""
    from nonebot_plugin_trade.candlebridge import PathState
    from nonebot_plugin_trade.market import build_model_parameters, encode_engine_state

    engine = PathState.create(build_model_parameters(), seed=seed)
    for key, value in overrides.items():
        setattr(engine, key, value)
    return encode_engine_state(engine)


def make_state(**overrides):
    from nonebot_plugin_trade.models import MarketState

    values = {
        "id": 1,
        "price": 10.0,
        "day": TRADE_DAY,
        "day_open": 10.0,
        "prev_close": 10.0,
        "engine_state": make_engine_state(),
        "float_shares": 100000,
        "last_tick_at": datetime(2026, 11, 19, 10, 0),
    }
    values.update(overrides)
    return MarketState(**values)


def make_holding(**overrides):
    from nonebot_plugin_trade.models import Holding

    values = {
        "user_id": FakeUser.user_id,
        "shares": 0,
        "frozen_shares": 0,
        "cost_basis": 0.0,
        "last_active_day": TRADE_DAY,
        "daily_bought": 0,
        "daily_sold": 0,
        "total_bought": 0.0,
        "total_sold": 0.0,
    }
    values.update(overrides)
    return Holding(**values)


def test_trading_time_boundaries():
    from nonebot_plugin_trade.market import is_trading_time, next_tick_time, target_tick_time, trading_day

    assert trading_day(datetime(2026, 11, 19, 7, 59)) == date(2026, 11, 18)
    assert trading_day(datetime(2026, 11, 19, 8, 0)) == date(2026, 11, 19)
    assert not is_trading_time(datetime(2026, 11, 19, 7, 59))
    assert is_trading_time(datetime(2026, 11, 19, 8, 0))
    assert is_trading_time(datetime(2026, 11, 19, 23, 59))
    assert not is_trading_time(datetime(2026, 11, 20, 0, 0))
    assert target_tick_time(datetime(2026, 11, 19, 14, 3)) == datetime(2026, 11, 19, 14, 0)
    assert target_tick_time(datetime(2026, 11, 19, 7, 30)) == datetime(2026, 11, 18, 23, 55)
    assert next_tick_time(datetime(2026, 11, 19, 8, 0)) == datetime(2026, 11, 19, 8, 5)
    assert next_tick_time(datetime(2026, 11, 19, 23, 55)) == datetime(2026, 11, 20, 8, 0)


def test_candlebridge_reference_hashes():
    """与上游 slwyts/candlebridge compatibility.test.ts 的三组参考哈希逐位一致"""
    import hashlib
    import json
    from dataclasses import replace

    from nonebot_plugin_trade.candlebridge import DEFAULT_MODEL, generate_candles

    def js_number(value: float) -> int | float:
        return int(value) if isinstance(value, float) and value.is_integer() else value

    cases = [
        ({}, "dcfa394c1ceddfcc0165e4d7b5fcd7a3204cf9175c3374e7a88edaaeb3171518"),
        (
            {"fine_seconds": 1, "fat_tail": False, "memory": False, "jumps": False, "regimes": False},
            "ee63a7fb2a70bc0ae5dc402795463150cd4d02f99960e3acbb39a3e5a58e09a1",
        ),
        (
            {"lock_target": False, "df": 4, "jump_probability": 1.0, "state_minimum": 1.0, "state_maximum": 3.0},
            "c2e277f2cd7f9f429a61a6bfdbbe8b9bfb1e16baf281eae625b8cafac016e60c",
        ),
    ]
    for overrides, expected_digest in cases:
        candles = generate_candles(
            start_price=100,
            end_price=102.4,
            count=35,
            interval_seconds=300,
            start_time=1_800_000_000_000,
            minimum_price=75,
            maximum_price=135,
            intensity="medium",
            seed=401,
            model=replace(DEFAULT_MODEL, **overrides),
        )
        rows = [
            [
                candle.open_time,
                candle.close_time,
                js_number(candle.open),
                js_number(candle.high),
                js_number(candle.low),
                js_number(candle.close),
                [[offset_ms, js_number(price)] for offset_ms, price in candle.points],
            ]
            for candle in candles
        ]
        digest = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode("utf-8")).hexdigest()
        assert digest == expected_digest


def test_candlebridge_validation_and_streaming_consistency():
    """流式 simulate_bar 与批量自由路径一致，且参数边界校验抛出对应错误码"""
    from dataclasses import replace

    from nonebot_plugin_trade.candlebridge import (
        DEFAULT_MODEL,
        CandleBridgeError,
        PathState,
        generate_candles,
        simulate_bar,
    )

    free_model = replace(DEFAULT_MODEL, lock_target=False, seed=402)
    batch = generate_candles(
        start_price=10.0,
        end_price=10.0,
        count=12,
        interval_seconds=300,
        start_time=1_800_000_000_000,
        minimum_price=1.0,
        maximum_price=100.0,
        seed=402,
        model=free_model,
    )

    stream_state = PathState.create(free_model, seed=402)
    price = 10.0
    streamed = []
    for _ in range(12):
        bar = simulate_bar(stream_state, price, 300, free_model, price_floor=0.01, price_decimals=8)
        streamed.append(bar)
        price = bar.close

    for ref, bar in zip(batch, streamed, strict=True):
        assert bar.open == pytest.approx(ref.open, abs=1e-6)
        assert bar.high == pytest.approx(ref.high, abs=1e-6)
        assert bar.low == pytest.approx(ref.low, abs=1e-6)
        assert bar.close == pytest.approx(ref.close, abs=1e-6)

    # 非法参数抛出带错误码的结构化异常
    with pytest.raises(CandleBridgeError) as error:
        generate_candles(
            start_price=0,
            end_price=10,
            count=5,
            interval_seconds=300,
            start_time=1_800_000_000_000,
            minimum_price=5,
            maximum_price=15,
        )
    assert error.value.code == "INVALID_PRICE_RANGE"

    with pytest.raises(CandleBridgeError) as error:
        generate_candles(
            start_price=10,
            end_price=10,
            count=5,
            interval_seconds=45,
            start_time=1_800_000_000_000,
            minimum_price=5,
            maximum_price=15,
        )
    assert error.value.code == "INVALID_INTERVAL"

    with pytest.raises(CandleBridgeError) as error:
        generate_candles(
            start_price=10,
            end_price=10,
            count=5,
            interval_seconds=300,
            start_time=1_800_000_000_000,
            minimum_price=5,
            maximum_price=15,
            model=replace(DEFAULT_MODEL, df=2),
        )
    assert error.value.code == "INVALID_PARAMETERS"


def test_engine_state_serialization_roundtrip():
    from nonebot_plugin_trade.candlebridge import DEFAULT_MODEL, PathState, sample_daily_model
    from nonebot_plugin_trade.market import decode_engine_state, encode_engine_state, get_engine_state

    original = PathState(rng_state=123456789, volatility=0.00042, regime=2, remaining=180, direction=-1)
    raw = encode_engine_state(original)
    assert decode_engine_state(raw) == original
    assert get_engine_state(make_state(engine_state=raw)) == original

    # 携带每日随机抽样的 daily_model 也能完整往返序列化
    sampled_model = sample_daily_model(PathState.create(DEFAULT_MODEL, seed=20261122), DEFAULT_MODEL)
    with_model = PathState(
        rng_state=987654321,
        volatility=0.00051,
        regime=1,
        remaining=90,
        direction=1,
        daily_model=sampled_model,
    )
    raw_with_model = encode_engine_state(with_model)
    restored = decode_engine_state(raw_with_model)
    assert restored == with_model
    assert restored is not None and restored.daily_model is not None
    assert restored.daily_model.lock_target is False

    # 空值、损坏 JSON、非对象或非法字段一律按未初始化处理
    assert decode_engine_state(None) is None
    assert decode_engine_state("") is None
    assert decode_engine_state("not json") is None
    assert decode_engine_state("[]") is None
    assert (
        decode_engine_state('{"rng_state": -1, "volatility": 0.1, "regime": 0, "remaining": 0, "direction": 1}') is None
    )
    assert decode_engine_state('{"rng_state": 1, "volatility": 0, "regime": 0, "remaining": 0, "direction": 1}') is None
    assert (
        decode_engine_state('{"rng_state": 1, "volatility": 0.1, "regime": 3, "remaining": 0, "direction": 1}') is None
    )
    assert (
        decode_engine_state('{"rng_state": 1, "volatility": 0.1, "regime": 0, "remaining": -1, "direction": 1}') is None
    )
    assert (
        decode_engine_state('{"rng_state": 1, "volatility": 0.1, "regime": 0, "remaining": 0, "direction": 0}') is None
    )
    assert (
        decode_engine_state(
            '{"rng_state": 1, "volatility": 0.1, "regime": 0, "remaining": 0, "direction": 1, "model": {"df": 1}}',
        )
        is None
    )


def test_daily_model_randomization_varies_across_days():
    """每天开盘重新抽取当日 CandleBridge 参数，同一种子可复现、不同交易日各具波动特征"""
    from nonebot_plugin_trade.candlebridge import DEFAULT_MODEL, PathState, sample_daily_model, sample_gap_minutes
    from nonebot_plugin_trade.market import get_engine_state, init_day

    state_a = make_state(engine_state=make_engine_state(seed=20261122))
    state_b = make_state(engine_state=make_engine_state(seed=20261122))
    init_day(state_a, TRADE_DAY)
    init_day(state_b, TRADE_DAY)
    engine_a = get_engine_state(state_a)
    engine_b = get_engine_state(state_b)
    assert engine_a is not None and engine_b is not None
    assert engine_a.daily_model is not None
    assert engine_a == engine_b

    # 连续多日抽样应出现不同的波动参数与跳空时长
    stream = PathState.create(DEFAULT_MODEL, seed=20261122)
    models = [sample_daily_model(stream, DEFAULT_MODEL) for _ in range(10)]
    gaps = [sample_gap_minutes(stream, 30) for _ in range(10)]
    assert len({m.base_volatility for m in models}) > 1
    assert len({m.intensity for m in models}) > 1
    assert len(set(gaps)) > 1
    assert all(15 <= gap <= 105 for gap in gaps)
    assert sample_gap_minutes(stream, 0) == 0


def test_open_gap_uses_candlebridge_state(monkeypatch: pytest.MonkeyPatch):
    """隔夜跳空沿用前一日尾盘的 CandleBridge 状态演进，不写 K 线，并保留状态续算"""
    from nonebot_plugin_trade import config as trade_config_module
    from nonebot_plugin_trade.market import apply_open_gap, get_engine_state

    # 默认开启动态随机时，同一种子与状态仍完全可复现
    state_a = make_state(
        price=10.0,
        engine_state=make_engine_state(seed=20261007, regime=2, remaining=1500, direction=1),
    )
    state_b = make_state(
        price=10.0,
        engine_state=make_engine_state(seed=20261007, regime=2, remaining=1500, direction=1),
    )
    before = get_engine_state(state_a)
    assert before is not None

    apply_open_gap(state_a)
    apply_open_gap(state_b)
    after = get_engine_state(state_a)
    assert after is not None
    assert state_a.day_open == state_b.day_open
    assert state_a.price == state_a.day_open
    assert state_a.engine_state == state_b.engine_state
    assert after.rng_state != before.rng_state
    assert after.regime == 2
    assert after.direction == 1
    assert after.remaining < before.remaining

    # 关闭动态随机时，严格按 trade_open_gap_minutes（30 分钟 / 5 秒 = 360 细步）演进
    monkeypatch.setattr(trade_config_module.config, "trade_randomize_daily_model", False)
    fixed_state = make_state(
        price=10.0,
        engine_state=make_engine_state(seed=20261007, regime=2, remaining=600, direction=1),
    )
    apply_open_gap(fixed_state)
    fixed_after = get_engine_state(fixed_state)
    assert fixed_after is not None
    assert fixed_after.remaining == 600 - 360

    # 关闭跳空（trade_open_gap_minutes=0）时保持原价不变
    monkeypatch.setattr(trade_config_module.config, "trade_open_gap_minutes", 0)
    unchanged = make_state(price=10.0)
    before_raw = unchanged.engine_state
    apply_open_gap(unchanged)
    assert unchanged.day_open == pytest.approx(10.0)
    assert unchanged.price == pytest.approx(10.0)
    assert unchanged.engine_state == before_raw


def test_candle_slot():
    from nonebot_plugin_trade.market import candle_slot, trade_candle_slot

    assert candle_slot(479) is None
    assert candle_slot(480) == 0
    assert candle_slot(485) == 0
    assert candle_slot(490) == 1
    assert candle_slot(1435) == 190

    assert trade_candle_slot(479) is None
    assert trade_candle_slot(480) == 0
    assert trade_candle_slot(485) == 1
    assert trade_candle_slot(490) == 2
    assert trade_candle_slot(600) == 24
    assert trade_candle_slot(1439) == 191


def test_impact_rate():
    from nonebot_plugin_trade.market import impact_rate

    assert impact_rate(0) == 0.0
    assert impact_rate(1) == pytest.approx(0.00001)
    assert impact_rate(100) == pytest.approx(0.001)
    assert impact_rate(1000) == pytest.approx(0.01)
    assert impact_rate(5000) == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_tick_generates_candlebridge_ohlc_and_respects_floor():
    from nonebot_plugin_trade.market import PRICE_FLOOR, apply_tick, get_engine_state
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    state = make_state(price=10.0, engine_state=make_engine_state(seed=401))
    before = get_engine_state(state)

    await apply_tick(state, datetime(2026, 11, 19, 9, 0), session)
    after = get_engine_state(state)
    assert after is not None and before is not None
    assert after.rng_state != before.rng_state

    first_candle = session.objects[(Candle, (TRADE_DAY, 11))]
    assert first_candle.open == pytest.approx(10.0)
    assert first_candle.close == pytest.approx(state.price)
    # 5 分钟内含 60 个 5 秒细步，天然形成上下影线
    assert first_candle.high >= max(first_candle.open, first_candle.close)
    assert first_candle.low <= min(first_candle.open, first_candle.close)
    assert first_candle.high > first_candle.low

    # 价格贴近地板价时，细步路径和收盘价均不会跌破 0.01
    state.price = PRICE_FLOOR
    await apply_tick(state, datetime(2026, 11, 19, 9, 5), session)
    floor_candle = session.objects[(Candle, (TRADE_DAY, 12))]
    assert state.price >= PRICE_FLOOR
    assert floor_candle.low >= PRICE_FLOOR
    assert floor_candle.high >= floor_candle.close >= PRICE_FLOOR


@pytest.mark.asyncio
async def test_ensure_market_cross_day():
    from nonebot_plugin_trade.market import PRICE_FLOOR, apply_open_gap, ensure_market, get_engine_state
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    with (
        patch("nonebot_plugin_trade.candlebridge.random_seed", return_value=20261007),
        patch("nonebot_plugin_trade.market.apply_open_gap", wraps=apply_open_gap) as gap,
    ):
        state = await ensure_market(session, datetime(2026, 11, 19, 14, 0))
        # 冷启动没有历史收盘价，不制造隔夜跳空
        assert gap.call_count == 0
        assert state.day == TRADE_DAY
        assert state.prev_close == pytest.approx(10.0)
        assert state.day_open == pytest.approx(10.0)
        assert state.last_tick_at == datetime(2026, 11, 19, 14, 0)
        assert len([key for key in session.objects if key[0] is Candle]) == 72
        assert state.price >= PRICE_FLOOR
        assert get_engine_state(state) is not None

        await ensure_market(session, datetime(2026, 11, 19, 23, 59))
        assert gap.call_count == 0
        assert state.day == TRADE_DAY
        assert state.last_tick_at == datetime(2026, 11, 19, 23, 55)
        assert len([key for key in session.objects if key[0] is Candle]) == 191
        close_price = state.price
        eod_engine = get_engine_state(state)
        assert eod_engine is not None

        await ensure_market(session, datetime(2026, 11, 20, 8, 0))
        # 08:00 沿用前一日尾盘的 CandleBridge 状态跳空，不写 K 线
        assert gap.call_count == 1
        assert state.day == date(2026, 11, 20)
        assert state.prev_close == pytest.approx(close_price)
        assert state.price == pytest.approx(state.day_open)
        assert state.last_tick_at == datetime(2026, 11, 20, 8, 0)
        assert len([key for key in session.objects if key[0] is Candle]) == 191
        open_engine = get_engine_state(state)
        assert open_engine is not None
        assert open_engine.rng_state != eod_engine.rng_state

        # 跳空每天只发生一次，08:05 起恢复正常 tick；当日首根 K 线从今开起步
        day_open = state.day_open
        await ensure_market(session, datetime(2026, 11, 20, 8, 5))
        assert gap.call_count == 1
        assert state.day_open == pytest.approx(day_open)
        assert state.last_tick_at == datetime(2026, 11, 20, 8, 5)
        assert len([key for key in session.objects if key[0] is Candle]) == 192
        first_candle = session.objects[(Candle, (date(2026, 11, 20), 0))]
        assert first_candle.open == pytest.approx(day_open)

        # 跨多日离线补算：每个 08:00 各跳一次
        await ensure_market(session, datetime(2026, 11, 22, 10, 0))
        assert gap.call_count == 3
        assert state.day == date(2026, 11, 22)
        assert state.last_tick_at == datetime(2026, 11, 22, 10, 0)
        assert state.price >= PRICE_FLOOR


@pytest.mark.asyncio
async def test_engine_state_persist_through_orm():
    """engine_state 以 JSON 文本落库：走真实 ORM 会话验证列类型与读写"""
    from nonebot_plugin_orm import get_session

    from nonebot_plugin_trade.candlebridge import PathState
    from nonebot_plugin_trade.market import encode_engine_state, get_engine_state
    from nonebot_plugin_trade.models import MarketState

    engine = PathState(rng_state=20261007, volatility=0.00031, regime=1, remaining=42, direction=-1)
    raw = encode_engine_state(engine)
    async with get_session() as session:
        await session.merge(
            MarketState(
                id=1,
                price=10.0,
                day_open=10.0,
                prev_close=10.0,
                engine_state=raw,
                float_shares=100000,
            ),
        )
        await session.commit()

    async with get_session() as session:
        state = await session.get(MarketState, 1)
        assert state is not None
        assert state.engine_state == raw
        assert get_engine_state(state) == engine


@pytest.mark.asyncio
async def test_ensure_market_initializes_engine_state_for_legacy_row():
    """从旧版本升级上来（engine_state 为空）时自动初始化 CandleBridge 状态并继续补算"""
    from nonebot_plugin_trade.market import ensure_market, get_engine_state

    session = FakeSession()
    session.add(make_state(engine_state=None, last_tick_at=datetime(2026, 11, 19, 10, 0)))

    with patch("nonebot_plugin_trade.candlebridge.random_seed", return_value=20261007):
        state = await ensure_market(session, datetime(2026, 11, 19, 10, 5))

    assert get_engine_state(state) is not None
    assert state.last_tick_at == datetime(2026, 11, 19, 10, 5)
    assert state.day == TRADE_DAY


@pytest.mark.asyncio
async def test_buy_fee_and_impact():
    from nonebot_plugin_trade.market import execute_buy
    from nonebot_plugin_trade.models import Candle, Holding

    session = FakeSession()
    state = make_state()
    user = FakeUser(2000)
    result = await execute_buy(session, state, user, "100", datetime(2026, 11, 19, 10, 0))

    assert result.shares == 100
    assert result.price == pytest.approx(10.0)
    assert result.gross == pytest.approx(1000.0)
    assert result.fee == pytest.approx(10.0)
    assert result.amount == pytest.approx(1010.0)
    assert result.impact == pytest.approx(0.001)
    assert result.new_price == pytest.approx(10.01)
    assert result.shares_after == 100
    assert result.frozen_after == 100
    assert result.sellable_after == 0
    assert result.daily_bought == 100
    assert result.balance_after == pytest.approx(990.0)
    assert state.float_shares == 99900

    holding = session.objects[(Holding, FakeUser.user_id)]
    assert holding.shares == 100
    assert holding.cost_basis == pytest.approx(1010.0)
    assert holding.total_bought == pytest.approx(1010.0)
    assert holding.total_sold == pytest.approx(0.0)

    candle = session.objects[(Candle, (TRADE_DAY, 24))]
    assert candle.open == pytest.approx(10.0)
    assert candle.close == pytest.approx(10.01)
    assert candle.volume == 100


@pytest.mark.asyncio
async def test_buy_all_and_percent():
    from nonebot_plugin_trade.market import execute_buy

    session = FakeSession()
    state = make_state()
    user = FakeUser(1000)
    result = await execute_buy(session, state, user, "all", datetime(2026, 11, 19, 10, 0))
    assert result.shares == 99
    assert result.amount == pytest.approx(999.9)
    assert result.balance_after == pytest.approx(0.1)

    session = FakeSession()
    state = make_state()
    user = FakeUser(1000)
    result = await execute_buy(session, state, user, "0.5", datetime(2026, 11, 19, 10, 0))
    assert result.shares == 49
    assert result.amount == pytest.approx(494.9)
    assert result.balance_after == pytest.approx(505.1)

    session = FakeSession()
    state = make_state()
    user = FakeUser(1000)
    result = await execute_buy(session, state, user, "50%", datetime(2026, 11, 19, 10, 0))
    assert result.shares == 49


@pytest.mark.asyncio
async def test_buy_limits_and_caps():
    from nonebot_plugin_trade.market import TradeError, execute_buy

    session = FakeSession()
    session.add(make_holding(daily_bought=1000))
    state = make_state()
    user = FakeUser(1000)
    with pytest.raises(TradeError) as error:
        await execute_buy(session, state, user, "1", datetime(2026, 11, 19, 10, 0))
    assert error.value.key == "error.daily_buy_limit"

    session = FakeSession()
    state = make_state(float_shares=10)
    user = FakeUser(1000)
    result = await execute_buy(session, state, user, "all", datetime(2026, 11, 19, 10, 0))
    assert result.shares == 10
    assert result.capped_reason == "float"

    session = FakeSession()
    session.add(make_holding(daily_bought=990))
    state = make_state()
    user = FakeUser(1000)
    result = await execute_buy(session, state, user, "all", datetime(2026, 11, 19, 10, 0))
    assert result.shares == 10
    assert result.capped_reason == "daily"


@pytest.mark.asyncio
async def test_sell_t_plus_1_and_daily_cap():
    from nonebot_plugin_trade.market import TradeError, execute_sell

    session = FakeSession()
    session.add(make_holding(shares=100, frozen_shares=100, cost_basis=1010.0))
    state = make_state(float_shares=99900)
    user = FakeUser()
    with pytest.raises(TradeError) as error:
        await execute_sell(session, state, user, "1", datetime(2026, 11, 19, 10, 0))
    assert error.value.key == "error.no_sellable"

    session = FakeSession()
    holding = make_holding(shares=100, frozen_shares=0, cost_basis=1010.0)
    session.add(holding)
    state = make_state(float_shares=99900)
    user = FakeUser()
    result = await execute_sell(session, state, user, "all", datetime(2026, 11, 19, 10, 0))
    assert result.shares == 100
    assert result.gross == pytest.approx(1000.0)
    assert result.fee == pytest.approx(10.0)
    assert result.amount == pytest.approx(990.0)
    assert result.impact == pytest.approx(0.001)
    assert result.new_price == pytest.approx(9.99)
    assert result.shares_after == 0
    assert holding.cost_basis == 0.0
    assert holding.total_sold == pytest.approx(990.0)
    assert state.float_shares == 100000
    assert user.vimcoin == pytest.approx(990.0)

    session = FakeSession()
    session.add(make_holding(shares=100, frozen_shares=0, cost_basis=1010.0, daily_sold=950))
    state = make_state(float_shares=99900)
    user = FakeUser()
    result = await execute_sell(session, state, user, "all", datetime(2026, 11, 19, 10, 0))
    assert result.shares == 50
    assert result.capped_reason == "daily"


@pytest.mark.asyncio
async def test_trade_totals_accumulate_across_rounds():
    """累计买入/卖出金额跨交易日累加，排行榜口径与逐笔记账一致"""
    from nonebot_plugin_trade.market import execute_buy, execute_sell
    from nonebot_plugin_trade.models import Holding

    session = FakeSession()
    state = make_state()
    user = FakeUser(2000)
    await execute_buy(session, state, user, "100", datetime(2026, 11, 19, 10, 0))
    holding = session.objects[(Holding, FakeUser.user_id)]
    assert holding.total_bought == pytest.approx(1010.0)
    assert holding.total_sold == pytest.approx(0.0)

    # 次日解冻后按当日价格清仓：累计卖出记录扣完手续费后的到账金额
    result = await execute_sell(session, state, user, "all", datetime(2026, 11, 20, 10, 0))
    assert result.amount == pytest.approx(990.99)
    assert holding.shares == 0
    assert holding.total_bought == pytest.approx(1010.0)
    assert holding.total_sold == pytest.approx(990.99)


def test_rank_holdings_values_open_positions_at_market_price():
    """持仓按当前价估值：未卖出的股票也计入收益率，不会因为没卖而被当成亏损"""
    from nonebot_plugin_trade.market import rank_holdings

    holdings = [
        make_holding(user_id="rank-holder", shares=100, cost_basis=1010.0, total_bought=1010.0),
        make_holding(user_id="rank-closed", shares=0, cost_basis=0.0, total_bought=1000.0, total_sold=1500.0),
        make_holding(user_id="rank-idle"),
    ]
    entries = rank_holdings(holdings, 12.0)

    assert [entry.user_id for entry in entries] == ["rank-closed", "rank-holder"]
    closed, holder = entries
    assert closed.rank == 1
    assert closed.market_value == pytest.approx(0.0)
    assert closed.profit == pytest.approx(500.0)
    assert closed.return_rate == pytest.approx(0.5)

    assert holder.rank == 2
    assert holder.market_value == pytest.approx(1200.0)
    assert holder.profit == pytest.approx(190.0)
    assert holder.return_rate == pytest.approx(190.0 / 1010.0)

    # 累计买入为 0 的用户（从未交易）不参与排行
    assert all(entry.user_id != "rank-idle" for entry in entries)


def test_rank_holdings_tie_break_is_stable():
    from nonebot_plugin_trade.market import rank_holdings

    holdings = [
        make_holding(user_id="rank-b", total_bought=100.0, total_sold=120.0),
        make_holding(user_id="rank-a", total_bought=100.0, total_sold=120.0),
    ]
    assert [entry.user_id for entry in rank_holdings(holdings, 10.0)] == ["rank-a", "rank-b"]


@pytest.mark.asyncio
async def test_load_ranking_uses_orm_rows_and_skips_untraded():
    from nonebot_plugin_orm import get_session
    from sqlalchemy import delete

    from nonebot_plugin_trade.market import load_ranking
    from nonebot_plugin_trade.models import Holding

    user_ids = ["rank-orm-holder", "rank-orm-closed", "rank-orm-idle"]
    async with get_session() as session:
        await session.execute(delete(Holding).where(Holding.user_id.in_(user_ids)))
        session.add(
            Holding(
                user_id="rank-orm-holder",
                shares=100,
                frozen_shares=0,
                cost_basis=1010.0,
                total_bought=1010.0,
                total_sold=0.0,
            ),
        )
        session.add(
            Holding(
                user_id="rank-orm-closed",
                shares=0,
                frozen_shares=0,
                cost_basis=0.0,
                total_bought=1000.0,
                total_sold=1500.0,
            ),
        )
        session.add(
            Holding(
                user_id="rank-orm-idle",
                shares=0,
                frozen_shares=0,
                cost_basis=0.0,
                total_bought=0.0,
                total_sold=0.0,
            ),
        )
        await session.commit()

    async with get_session() as session:
        entries = await load_ranking(session, 10.0)

    by_id = {entry.user_id: entry for entry in entries}
    assert "rank-orm-idle" not in by_id
    assert by_id["rank-orm-closed"].return_rate == pytest.approx(0.5)
    assert by_id["rank-orm-holder"].return_rate == pytest.approx(-10.0 / 1010.0)
    assert by_id["rank-orm-closed"].rank < by_id["rank-orm-holder"].rank
    assert [entry.return_rate for entry in entries] == sorted(
        (entry.return_rate for entry in entries),
        reverse=True,
    )


@pytest.mark.asyncio
async def test_legacy_holding_sold_after_launch_keeps_backfilled_cost():
    """排行上线前的旧仓：迁移回填的买入成本必须参与卖出后的收益率计算"""
    from nonebot_plugin_trade.market import execute_sell, rank_holdings

    session = FakeSession()
    # 模拟迁移后的旧仓：total_bought 已按 cost_basis 回填
    holding = make_holding(shares=100, frozen_shares=0, cost_basis=1010.0, total_bought=1010.0)
    session.add(holding)
    state = make_state(price=12.0, float_shares=99900)
    user = FakeUser()

    result = await execute_sell(session, state, user, "all", datetime(2026, 11, 19, 10, 0))

    assert result.amount == pytest.approx(1188.0)
    assert holding.total_bought == pytest.approx(1010.0)
    assert holding.total_sold == pytest.approx(1188.0)
    entry = rank_holdings([holding], 12.0)[0]
    # 收益率以“卖出到账 / 上线前买入成本”计算，而不是只把卖出值当成收益
    assert entry.return_rate == pytest.approx(1188.0 / 1010.0 - 1)


@pytest.mark.asyncio
async def test_rank_text_lists_top_and_my_rank(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import config as trade_config_module
    from nonebot_plugin_trade.__main__ import build_rank_text
    from nonebot_plugin_trade.market import rank_holdings

    monkeypatch.setattr(trade_config_module.config, "trade_rank_size", 2)
    entries = rank_holdings(
        [
            make_holding(user_id="rank-u1", total_bought=1000.0, total_sold=1500.0),
            make_holding(user_id="rank-u2", total_bought=1000.0, total_sold=1200.0),
            make_holding(user_id="rank-me", total_bought=1000.0, total_sold=1100.0),
        ],
        10.0,
    )
    text = await build_rank_text(
        "rank-me",
        entries,
        {"rank-u1": "小满", "rank-u2": "阿岚", "rank-me": "我"},
    )

    assert "📊 Moonlark 证券交易所 · 收益排行榜" in text
    assert "🥇 1. 小满  +50.00% · 盈亏 +500.00（买入 1,000.00 / 卖出 1,500.00）" in text
    assert "2. 阿岚  +20.00% · 盈亏 +200.00（买入 1,000.00 / 卖出 1,200.00）" in text
    assert "仅显示前 2 名，共 3 人上榜。" in text
    assert "你的排名：第 3 名 · +10.00%（盈亏 +100.00，买入 1,000.00 / 卖出 1,100.00）" in text


@pytest.mark.asyncio
async def test_rank_text_handles_empty_ranking_and_untraded_user():
    from nonebot_plugin_trade.__main__ import build_rank_text
    from nonebot_plugin_trade.market import rank_holdings

    empty = await build_rank_text("rank-nobody", [], {})
    assert empty == "暂时还没有人交易，开市后买入股票就能登上收益排行榜。"

    entries = rank_holdings([make_holding(user_id="rank-someone", total_bought=1000.0, total_sold=1200.0)], 10.0)
    untraded = await build_rank_text("rank-newbie", entries, {"rank-someone": "小满"})
    assert "1. 小满  +20.00%" in untraded
    assert "你还没有交易记录，买入股票后才会进入排行榜。" in untraded


@pytest.mark.asyncio
async def test_ranking_entry_data_uses_display_and_info():
    """ranking 插件用 data 排序、display 展示，info 作为昵称下方的说明"""
    from nonebot_plugin_trade.market import rank_holdings
    from nonebot_plugin_trade.ranking import ranking_entry_data

    entry = rank_holdings(
        [make_holding(user_id="rank-image", total_bought=1000.0, total_sold=1200.0)],
        10.0,
    )[0]
    data = await ranking_entry_data(entry, "tester")

    assert data["user_id"] == "rank-image"
    assert data["data"] == pytest.approx(20.0)
    assert data["display"] == "+20.00%"
    assert data["info"] == "买入 1,000.00 / 卖出 1,200.00"


@pytest.mark.asyncio
async def test_render_ranking_image_uses_ranking_plugin(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import ranking as trade_ranking
    from nonebot_plugin_trade.market import rank_holdings

    captured: dict[str, object] = {}

    async def fake_generate_image(
        ranked_data: list[dict[str, object]],
        user_id: str,
        title: str,
        limit: int = 7,
    ) -> bytes:
        captured.update(ranked_data=ranked_data, user_id=user_id, title=title, limit=limit)
        return b"rank-png"

    monkeypatch.setattr(trade_ranking, "generate_image", fake_generate_image)
    entries = rank_holdings(
        [make_holding(user_id="rank-image", total_bought=1000.0, total_sold=1200.0)],
        10.0,
    )
    image = await trade_ranking.render_ranking_image(entries, "tester")

    assert image == b"rank-png"
    assert captured["user_id"] == "tester"
    assert captured["limit"] == 10
    assert "收益排行榜" in str(captured["title"])
    assert captured["ranked_data"] == [
        {
            "user_id": "rank-image",
            "data": 20.0,
            "display": "+20.00%",
            "info": "买入 1,000.00 / 卖出 1,200.00",
        },
    ]


@pytest.mark.asyncio
async def test_render_ranking_image_falls_back_when_render_fails(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import ranking as trade_ranking
    from nonebot_plugin_trade.market import rank_holdings

    async def broken_generate_image(*_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError("browser not available")

    monkeypatch.setattr(trade_ranking, "generate_image", broken_generate_image)
    entries = rank_holdings(
        [make_holding(user_id="rank-image", total_bought=1000.0, total_sold=1200.0)],
        10.0,
    )
    assert await trade_ranking.render_ranking_image(entries, "tester") is None


@pytest.mark.asyncio
async def test_web_ranking_handle_returns_display_value(monkeypatch: pytest.MonkeyPatch):
    """Web API 的 users / me 都应展示 display（+20.00%），不能退化成裸数字"""
    from nonebot_plugin_ranking import generator, web

    from nonebot_plugin_trade import ranking as trade_ranking
    from nonebot_plugin_trade.market import rank_holdings

    entries = rank_holdings(
        [make_holding(user_id="rank-web", total_bought=1000.0, total_sold=1200.0)],
        10.0,
    )

    async def fake_entries():
        return entries

    fake_user = MagicMock()
    fake_user.get_nickname.return_value = "小满"
    monkeypatch.setattr(trade_ranking, "load_ranking_entries", fake_entries)
    monkeypatch.setattr(web, "get_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(generator, "get_user", AsyncMock(return_value=fake_user))

    response = await trade_ranking.trade_ranking.handle(MagicMock(), offset=0, limit=20, user_id="rank-web")

    assert response["total"] == 1
    assert response["users"][0]["data"] == "+20.00%"
    assert response["me"] is not None
    assert response["me"]["data"] == "+20.00%"


@pytest.mark.asyncio
async def test_web_ranking_exposes_same_ranking_data(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import ranking as trade_ranking
    from nonebot_plugin_trade.market import rank_holdings

    entries = rank_holdings(
        [make_holding(user_id="rank-web", total_bought=1000.0, total_sold=1200.0)],
        10.0,
    )

    async def fake_entries():
        return entries

    monkeypatch.setattr(trade_ranking, "load_ranking_entries", fake_entries)
    data = await trade_ranking.trade_ranking.get_sorted_data("tester")

    assert data[0]["user_id"] == "rank-web"
    assert data[0]["data"] == pytest.approx(20.0)
    assert data[0]["display"] == "+20.00%"
    assert data[0]["info"] == "买入 1,000.00 / 卖出 1,200.00"


def test_parse_amounts():
    from nonebot_plugin_trade.market import TradeError, parse_buy_amount, parse_sell_amount

    assert parse_buy_amount("all").kind == "all"
    assert parse_buy_amount("100").kind == "shares"
    assert parse_buy_amount("100").value == 100
    assert parse_buy_amount("0.5").kind == "percent"
    assert parse_buy_amount("0.5").value == pytest.approx(0.5)
    assert parse_buy_amount("50%").value == pytest.approx(0.5)
    assert parse_buy_amount("100%").value == pytest.approx(1.0)

    for invalid in ("0", "-1", "abc", "1.5", "0.5.1"):
        with pytest.raises(TradeError):
            parse_buy_amount(invalid)

    assert parse_sell_amount("all").kind == "all"
    assert parse_sell_amount("100").value == 100
    for invalid in ("0", "-1", "abc", "0.5", "50%"):
        with pytest.raises(TradeError):
            parse_sell_amount(invalid)


@pytest.mark.asyncio
async def test_buy_before_first_tick_updates_candle():
    from nonebot_plugin_trade.market import execute_buy
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    state = make_state(last_tick_at=datetime(2026, 11, 19, 8, 0))
    user = FakeUser(2000)
    await execute_buy(session, state, user, "100", datetime(2026, 11, 19, 8, 2))

    candle = session.objects[(Candle, (TRADE_DAY, 0))]
    assert candle.open == pytest.approx(10.0)
    assert candle.close == pytest.approx(10.01)
    assert candle.volume == 100


def test_chart_renders_png():
    from nonebot_plugin_trade.chart import CandlePoint, render_kline_chart

    points = [
        CandlePoint(day=date(2026, 11, 18), slot=189, open=9.9, high=10.0, low=9.8, close=9.95),
        CandlePoint(day=date(2026, 11, 18), slot=190, open=9.95, high=10.1, low=9.9, close=10.05),
        CandlePoint(day=date(2026, 11, 19), slot=0, open=10.2, high=10.3, low=10.1, close=10.25, volume=10),
    ]
    data = render_kline_chart(date(2026, 11, 19), points, "test", "empty", reference_price=10.2, visible_candles=8)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    empty = render_kline_chart(date(2026, 11, 19), [], "test", "empty")
    assert empty.startswith(b"\x89PNG\r\n\x1a\n")


def test_daily_chart_renders_png():
    from nonebot_plugin_trade.chart import DailyCandlePoint, render_daily_kline_chart

    points = [
        DailyCandlePoint(day=date(2026, 11, 18), open=9.9, high=10.1, low=9.8, close=10.0, volume=100),
        DailyCandlePoint(day=date(2026, 11, 19), open=10.2, high=10.5, low=10.0, close=10.3, volume=250),
    ]
    data = render_daily_kline_chart(points, "test", "empty", visible_candles=60)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    empty = render_daily_kline_chart([], "test", "empty")
    assert empty.startswith(b"\x89PNG\r\n\x1a\n")


def test_daily_chart_keeps_candles_adjacent_when_data_insufficient(monkeypatch: pytest.MonkeyPatch):
    """数据不足时蜡烛仍按 1 个 slot 紧挨着排在右侧，不在横轴方向上拉开空隙"""
    from matplotlib.axes import Axes

    from nonebot_plugin_trade.chart import DailyCandlePoint, render_daily_kline_chart

    positions: list[float] = []
    original = Axes.vlines

    def spy_vlines(self, x: float, ymin: float, ymax: float, *args: object, **kwargs: object) -> object:
        positions.append(x)
        return original(self, x, ymin, ymax, *args, **kwargs)

    monkeypatch.setattr(Axes, "vlines", spy_vlines)
    points = [
        DailyCandlePoint(
            day=date(2026, 11, 17) + timedelta(days=index),
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.2,
        )
        for index in range(3)
    ]

    render_daily_kline_chart(points, "test", "empty", visible_candles=60)

    # total=60、只有 3 根：位置是 57/58/59，左侧留白而不是把 3 根蜡烛铺满整条横轴
    assert positions == [57, 58, 59]


def test_day_tick_indexes_skip_overlapping_labels():
    from itertools import pairwise

    from nonebot_plugin_trade.chart import _day_tick_indexes

    # 只有 3 根蜡烛时，相邻日期标签会重叠，只保留最新一根的日期
    assert _day_tick_indexes(3, 60) == [2]

    indexes = _day_tick_indexes(60, 60)
    assert indexes[-1] == 59
    assert all(right - left >= 3 for left, right in pairwise(indexes))


@pytest.mark.asyncio
async def test_load_recent_candles_spans_days_in_ascending_order():
    from nonebot_plugin_trade.market import load_recent_candles
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    for day, slot in ((date(2026, 11, 18), 190), (date(2026, 11, 19), 0), (date(2026, 11, 19), 1)):
        session.add(Candle(day=day, slot=slot, open=10.0, high=10.0, low=10.0, close=10.0))

    candles = await load_recent_candles(session, 120)

    assert [(candle.day, candle.slot) for candle in candles] == [
        (date(2026, 11, 18), 190),
        (date(2026, 11, 19), 0),
        (date(2026, 11, 19), 1),
    ]


@pytest.mark.asyncio
async def test_load_daily_candles_aggregates_ohlc_and_volume():
    from nonebot_plugin_trade.market import DailyCandle, load_daily_candles
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    session.add(Candle(day=date(2026, 11, 17), slot=0, open=10.0, high=10.4, low=9.8, close=10.2))
    session.add(Candle(day=date(2026, 11, 17), slot=1, open=10.2, high=10.6, low=10.1, close=10.5, volume=30))
    session.add(Candle(day=date(2026, 11, 18), slot=0, open=10.5, high=10.9, low=10.4, close=10.8, volume=20))
    session.add(Candle(day=date(2026, 11, 18), slot=1, open=10.8, high=11.0, low=10.7, close=10.9, volume=5))

    daily = await load_daily_candles(session, 2)

    assert daily == [
        DailyCandle(day=date(2026, 11, 17), open=10.0, high=10.6, low=9.8, close=10.5, volume=30),
        DailyCandle(day=date(2026, 11, 18), open=10.5, high=11.0, low=10.4, close=10.9, volume=25),
    ]

    # limit 只保留最近若干交易日；非正数直接返回空
    assert [candle.day for candle in await load_daily_candles(session, 1)] == [date(2026, 11, 18)]
    assert await load_daily_candles(session, 0) == []


@pytest.mark.asyncio
async def test_history_caption_and_render_use_named_placeholders():
    from nonebot_plugin_trade.__main__ import build_history_caption, render_daily_chart
    from nonebot_plugin_trade.chart import DailyCandlePoint

    points = [
        DailyCandlePoint(day=date(2026, 11, 18), open=10.0, high=10.4, low=9.8, close=10.2),
        DailyCandlePoint(day=date(2026, 11, 19), open=10.2, high=10.6, low=10.1, close=10.5),
    ]
    caption = await build_history_caption("tester", points)
    assert "2026-11-19" in caption
    assert "10.50" in caption
    assert "已积累 2 个交易日" in caption

    with patch("nonebot_plugin_trade.__main__.render_daily_kline_chart", return_value=b"png"):
        assert await render_daily_chart("tester", points) == b"png"


def test_rank_subcommand_parses():
    """新增 rank 子命令及其别名都必须能被 Alconna 解析，否则指令会静默无响应"""
    from nonebot_plugin_trade.__main__ import trade

    command = trade.command()
    assert command.parse("/trade rank").matched
    assert command.parse("/trade ranking").matched
    assert command.parse("/trade").matched


def test_help_does_not_expose_internal_mechanism():
    import re
    from pathlib import Path

    import yaml

    path = Path(__file__).parent.parent / "src" / "lang" / "zh_hans" / "trade.yaml"
    help_yaml = Path(__file__).parent.parent / "src" / "plugins" / "nonebot_plugin_trade" / "help.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    help_cfg = yaml.safe_load(help_yaml.read_text(encoding="utf-8"))
    details = data["help"]["details"]
    assert "标签" not in details
    assert "目标时间" not in details
    assert "11:00" not in details
    assert "20:00" not in details
    # 面板不再展示流通股数，帮助里也不应出现总股本
    assert "100000" not in details
    # 隔夜跳空是玩家可见的行情机制，帮助需要说明
    assert "隔夜跳空" in details
    # 避免在 Markdown 渲染时把尖括号当成 HTML 标签吞掉，或 4 空格缩进触发代码块
    assert not re.search(r"<[^>\n]+>", details)
    assert not any(line.startswith("    ") for line in details.splitlines())

    usage_keys = [key.removeprefix("help.") for key in help_cfg["commands"]["trade"]["usages"]]
    for key in usage_keys:
        usage = data["help"][key]
        match = re.search(r"\s*\([^)]*\)\s*$", usage)
        assert match is not None, f"{key} 缺少末尾 (说明) 或含嵌套圆括号: {usage}"
        assert usage[: match.start()].strip().startswith("trade")


def test_keyboard_row():
    from nonebot_plugin_trade.__main__ import _keyboard_row

    assert _keyboard_row(3) is None
    assert _keyboard_row(4) == 2
    assert _keyboard_row(5) == 3


@pytest.mark.asyncio
async def test_trade_keyboard_buttons():
    from nonebot_plugin_trade import __main__ as trade_main

    with (
        patch.object(trade_main.lang, "text", new=AsyncMock(return_value="按钮")),
        patch.object(trade_main, "get_command_prefix", return_value="/"),
    ):
        buttons = await trade_main.build_trade_keyboard("10001")

    assert [button.text for button in buttons] == [
        "/trade buy ",
        "/trade buy all",
        "/trade sell ",
        "/trade sell all",
        "/trade",
    ]
    # 买入/卖出按钮改成 input 类型：点击只预填指令，股数由用户自己填（enter 会直接发出固定数量）
    assert [button.flag for button in buttons] == ["input", "enter", "input", "enter", "enter"]
    assert buttons[0].label == "按钮"
    assert buttons[2].label == "按钮"


@pytest.mark.asyncio
async def test_chart_title_uses_named_date_placeholder():
    """回归：chart.title 的模板使用命名占位符 ``{date}`` / ``{count}``。

    渲染 K 线时必须按关键字传参；传位置参数会让 ``str.format`` 抛
    ``KeyError``，异常被 nonebot 吞掉后 ``/trade`` 静默无响应
    （私聊、群聊与适配器无关）。
    """
    from nonebot_plugin_trade.__main__ import lang, render_chart

    title = await lang.text("chart.title", "tester", date="2026-11-19", count=120)
    assert "2026-11-19" in title
    assert "120" in title

    with patch("nonebot_plugin_trade.__main__.render_kline_chart", return_value=b"png"):
        assert await render_chart("tester", TRADE_DAY, [], 10.0) == b"png"


@pytest.mark.asyncio
async def test_render_chart_falls_back_when_text_formatting_fails(monkeypatch: pytest.MonkeyPatch):
    """文案格式化失败时不应让整条 /trade 静默失败，应回退到文本消息"""
    from nonebot_plugin_trade import __main__ as trade_main

    monkeypatch.setattr(trade_main.lang, "text", AsyncMock(side_effect=KeyError("date")))
    assert await trade_main.render_chart("tester", TRADE_DAY, [], 10.0) is None


def make_panel_data(
    state_overrides: dict | None = None,
    holding_overrides: dict | None = None,
    now: datetime | None = None,
):
    from nonebot_plugin_trade.panel import build_panel_data

    return build_panel_data(
        make_state(**(state_overrides or {})),
        make_holding(**(holding_overrides or {})),
        now or datetime(2026, 11, 19, 10, 0),
    )


@pytest.mark.asyncio
async def test_panel_markdown_has_hierarchy_and_hides_float_shares():
    from nonebot_plugin_trade.panel import build_panel_markdown

    data = make_panel_data(
        {"price": 10.5, "day_open": 10.0, "prev_close": 9.9},
        {"shares": 200, "frozen_shares": 100, "cost_basis": 2000.0, "daily_bought": 100},
    )
    markdown = await build_panel_markdown("panel-user", data)

    assert markdown.startswith("## 📈 Moonlark 证券交易所")
    assert "**交易中**" in markdown
    assert "### 行情" in markdown
    assert "- **最新价**：**10.50 VimCoin**" in markdown
    assert r"- 今日涨跌：\(\color{red}{\blacktriangle\ {+6.06\%}}\)（+0.60）" in markdown
    assert "- 今开 10.00（跳空 +1.01%） · 昨收 9.90" in markdown
    assert "### 我的持仓" in markdown
    assert "- 持股 **200** 股 · 可卖 100 股 · 冻结 100 股" in markdown
    assert "- 成本 **10.00 VimCoin**" in markdown
    assert r"- 浮动盈亏 \(\color{red}{+100.00}\) VimCoin（\(\color{red}{+5.00\%}\)）" in markdown
    assert "### 今日交易" in markdown
    assert "- 买入 **100/1000** 股" in markdown
    assert "市场流通" not in markdown
    assert "100000" not in markdown


@pytest.mark.asyncio
async def test_panel_markdown_renders_change_text_as_colored_formula():
    """涨跌文本用 LaTeX 行内公式显示：红涨绿跌，平盘用灰色

    QQ 官方 markdown 没有给文字上色的语法，``\\(...\\)`` 会交给公式渲染器，
    ``\\color{...}`` 才能上色；公式里的 ``%`` 必须转义，否则会被当成 LaTeX 注释。
    """
    from nonebot_plugin_trade.panel import build_panel_markdown

    up = await build_panel_markdown("panel-user", make_panel_data({"price": 10.5, "prev_close": 10.0}))
    assert r"\(\color{red}{\blacktriangle\ {+5.00\%}}\)（+0.50）" in up

    down = await build_panel_markdown("panel-user", make_panel_data({"price": 9.5, "prev_close": 10.0}))
    assert r"\(\color{green}{\blacktriangledown\ {-5.00\%}}\)（-0.50）" in down

    flat = await build_panel_markdown("panel-user", make_panel_data({"price": 10.0, "prev_close": 10.0}))
    assert r"\(\color{gray}{\cdot\ {+0.00\%}}\)（+0.00）" in flat


@pytest.mark.asyncio
async def test_panel_markdown_renders_profit_text_as_colored_formula():
    """浮动盈亏与盈亏比例同样用 LaTeX 行内公式上色：盈利红、亏损绿、持平灰"""
    from nonebot_plugin_trade.panel import build_panel_markdown

    holding = {"shares": 200, "frozen_shares": 0, "cost_basis": 2000.0}
    gain = await build_panel_markdown("panel-user", make_panel_data({"price": 10.5}, holding))
    assert r"浮动盈亏 \(\color{red}{+100.00}\) VimCoin（\(\color{red}{+5.00\%}\)）" in gain

    loss = await build_panel_markdown("panel-user", make_panel_data({"price": 9.5}, holding))
    assert r"浮动盈亏 \(\color{green}{-100.00}\) VimCoin（\(\color{green}{-5.00\%}\)）" in loss

    flat = await build_panel_markdown("panel-user", make_panel_data({"price": 10.0}, holding))
    assert r"浮动盈亏 \(\color{gray}{+0.00}\) VimCoin（\(\color{gray}{+0.00\%}\)）" in flat


@pytest.mark.asyncio
async def test_panel_markdown_closed_market_and_empty_holding():
    from nonebot_plugin_trade.panel import build_panel_markdown

    data = make_panel_data(now=datetime(2026, 11, 19, 7, 0))
    markdown = await build_panel_markdown("panel-user", data)

    assert "**休市**" in markdown
    assert "- 暂无持仓" in markdown
    assert "浮动盈亏" not in markdown


@pytest.mark.asyncio
async def test_panel_text_fallback_hides_float_shares():
    from nonebot_plugin_trade.panel import build_panel_text

    data = make_panel_data(
        {"price": 10.5, "day_open": 10.0, "prev_close": 9.9},
        {"shares": 200, "frozen_shares": 0, "cost_basis": 2000.0},
    )
    text = await build_panel_text("panel-user", data)

    assert "📈 Moonlark 证券交易所" in text
    assert "状态：交易中（08:00–24:00）" in text
    assert "当前价格：10.50 VimCoin" in text
    assert "今日涨跌：▲ +6.06%（+0.60）" in text
    assert "\\(" not in text
    assert "今开：10.00 VimCoin（跳空 +1.01%） · 昨收：9.90 VimCoin" in text
    assert "你的持股：200 股（可卖 200 股，冻结 0 股）" in text
    assert "市场流通" not in text
    assert "100000" not in text


class _FakeUniMessage:
    """只记录 image 段的 UniMessage 替身"""

    def __init__(self) -> None:
        self.images: list[bytes] = []

    def image(self, raw: bytes = b"", **_kwargs: object) -> "_FakeUniMessage":
        self.images.append(raw)
        return self

    def __add__(self, other: "_FakeUniMessage") -> "_FakeUniMessage":
        self.images += other.images
        return self

    async def send(self, **_kwargs: object) -> None:
        return None


@pytest.mark.asyncio
async def test_send_panel_renders_markdown_image_for_other_adapters(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import __main__ as trade_main

    rendered: dict[str, str] = {}
    sent: dict[str, _FakeUniMessage] = {}

    async def fake_md_to_pic(markdown: str) -> bytes:
        rendered["markdown"] = markdown
        return b"panel-image"

    class RecordingUniMessage(_FakeUniMessage):
        async def send(self, **_kwargs: object) -> None:
            sent["message"] = self

    monkeypatch.setattr(trade_main, "md_to_pic", fake_md_to_pic)
    monkeypatch.setattr(trade_main, "UniMessage", RecordingUniMessage)
    finished = AsyncMock()
    monkeypatch.setattr(trade_main.trade, "finish", finished)

    await trade_main.send_panel(MagicMock(), MagicMock(), "panel-user", make_panel_data(), b"chart-image")

    assert "## 📈 Moonlark 证券交易所" in rendered["markdown"]
    assert sent["message"].images == [b"panel-image", b"chart-image"]
    finished.assert_awaited()


@pytest.mark.asyncio
async def test_send_panel_falls_back_to_text_when_image_render_fails(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import __main__ as trade_main

    async def broken_md_to_pic(_markdown: str) -> bytes:
        raise RuntimeError("browser not available")

    fallback = AsyncMock()
    monkeypatch.setattr(trade_main, "md_to_pic", broken_md_to_pic)
    monkeypatch.setattr(trade_main, "send_plain_panel", fallback)

    await trade_main.send_panel(MagicMock(), MagicMock(), "panel-user", make_panel_data(), None)

    fallback.assert_awaited()


class _FakeHistoryMessage(_FakeUniMessage):
    """记录 text 段与 image 段的 UniMessage 替身"""

    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []

    def text(self, content: str = "", **_kwargs: object) -> "_FakeHistoryMessage":
        self.texts.append(content)
        return self

    def __add__(self, other: "_FakeHistoryMessage") -> "_FakeHistoryMessage":
        merged = type(self)()
        merged.texts = self.texts + other.texts
        merged.images = self.images + other.images
        return merged


@pytest.mark.asyncio
async def test_send_history_chart_sends_caption_and_image_for_other_adapters(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import __main__ as trade_main

    sent: dict[str, _FakeHistoryMessage] = {}

    class RecordingUniMessage(_FakeHistoryMessage):
        async def send(self, **_kwargs: object) -> None:
            sent["message"] = self

    monkeypatch.setattr(trade_main, "UniMessage", RecordingUniMessage)
    finished = AsyncMock()
    monkeypatch.setattr(trade_main.trade, "finish", finished)

    await trade_main.send_history_chart(MagicMock(), MagicMock(), "日 K 说明", b"chart-image")

    assert sent["message"].texts == ["日 K 说明"]
    assert sent["message"].images == [b"chart-image"]
    finished.assert_awaited()


@pytest.mark.asyncio
async def test_send_history_chart_uses_markdown_image_for_qq(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import __main__ as trade_main

    class FakeQQBot:
        pass

    record: dict[str, object] = {}

    class FakeMessage:
        def style(self, text: str, _kind: str) -> "FakeMessage":
            record["text"] = text
            return self

        async def send(self, **_kwargs: object) -> None:
            record["sent"] = True

    async def fake_create_image_markdown(_chart: bytes, _bot: object) -> str:
        return "![日 K](qqbot-media://example)"

    monkeypatch.setattr(trade_main, "QQBot", FakeQQBot)
    monkeypatch.setattr(trade_main, "create_image_markdown", fake_create_image_markdown)
    monkeypatch.setattr(trade_main, "UniMessage", FakeMessage)
    finished = AsyncMock()
    monkeypatch.setattr(trade_main.trade, "finish", finished)

    await trade_main.send_history_chart(FakeQQBot(), MagicMock(), "日 K 说明", b"chart")

    assert record["text"] == "日 K 说明\n\n![日 K](qqbot-media://example)"
    assert record["sent"] is True
    finished.assert_awaited()


@pytest.mark.asyncio
async def test_send_history_chart_falls_back_to_caption(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import __main__ as trade_main

    finished = AsyncMock()
    monkeypatch.setattr(trade_main.trade, "finish", finished)

    await trade_main.send_history_chart(MagicMock(), MagicMock(), "暂无日 K 数据", None)

    finished.assert_awaited_once_with("暂无日 K 数据")


@pytest.mark.asyncio
async def test_send_rank_image_sends_image_for_other_adapters(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import __main__ as trade_main

    sent: dict[str, _FakeUniMessage] = {}

    class RecordingUniMessage(_FakeUniMessage):
        async def send(self, **_kwargs: object) -> None:
            sent["message"] = self

    monkeypatch.setattr(trade_main, "UniMessage", RecordingUniMessage)
    finished = AsyncMock()
    monkeypatch.setattr(trade_main.trade, "finish", finished)

    await trade_main.send_rank_image(MagicMock(), MagicMock(), "rank-user", [], b"rank-image")

    assert sent["message"].images == [b"rank-image"]
    finished.assert_awaited()


@pytest.mark.asyncio
async def test_send_rank_image_uses_markdown_for_qq(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import __main__ as trade_main

    class FakeQQBot:
        pass

    sent: dict[str, str] = {}

    async def fake_create_image_markdown(_image: bytes, _bot: object) -> str:
        return "![收益排行](qqbot-media://rank)"

    async def fake_send_trade_text_with_keyboard(_bot: object, _event: object, _user_id: str, text: str) -> None:
        sent["text"] = text

    monkeypatch.setattr(trade_main, "QQBot", FakeQQBot)
    monkeypatch.setattr(trade_main, "create_image_markdown", fake_create_image_markdown)
    monkeypatch.setattr(trade_main, "send_trade_text_with_keyboard", fake_send_trade_text_with_keyboard)

    await trade_main.send_rank_image(FakeQQBot(), MagicMock(), "rank-user", [], b"rank-image")

    assert sent["text"] == "![收益排行](qqbot-media://rank)"


@pytest.mark.asyncio
async def test_send_panel_appends_chart_image_markdown_for_qq(monkeypatch: pytest.MonkeyPatch):
    from nonebot_plugin_trade import __main__ as trade_main

    class FakeQQBot:
        pass

    sent: dict[str, str] = {}

    async def fake_create_image_markdown(_chart: bytes, _bot: object) -> str:
        return "![K 线](qqbot-media://example)"

    async def fake_send_trade_text_with_keyboard(_bot: object, _event: object, _user_id: str, text: str) -> None:
        sent["text"] = text

    monkeypatch.setattr(trade_main, "QQBot", FakeQQBot)
    monkeypatch.setattr(trade_main, "create_image_markdown", fake_create_image_markdown)
    monkeypatch.setattr(trade_main, "send_trade_text_with_keyboard", fake_send_trade_text_with_keyboard)

    await trade_main.send_panel(FakeQQBot(), MagicMock(), "panel-user", make_panel_data(), b"chart")

    assert sent["text"].startswith("## 📈 Moonlark 证券交易所")
    assert sent["text"].endswith("![K 线](qqbot-media://example)")


def test_panel_change_uses_previous_close_when_gap_down():
    """跳空低开且价格低于昨收：按昨收计显示下跌；若按今开计会误显示上涨"""
    data = make_panel_data({"price": 9.9, "day_open": 9.7, "prev_close": 10.0})

    assert data.change == "-0.10"
    assert data.change_pct == "-1.00%"
    assert data.gap_pct == "-3.00%"
    assert data.trend == "▼"


@pytest.mark.asyncio
async def test_tick_keeps_trade_extremes():
    """tick 的 CandleBridge 路径只扩展、不覆盖成交写入的 high/low"""
    from nonebot_plugin_trade.candlebridge import SimulatedBar
    from nonebot_plugin_trade.market import apply_tick, update_candle_on_trade
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    state = make_state(price=10.5)
    await update_candle_on_trade(session, state, datetime(2026, 11, 19, 8, 55), 10.0, 10.5, 100)
    candle = session.objects[(Candle, (TRADE_DAY, 11))]
    assert candle.high == pytest.approx(10.5)
    assert candle.low == pytest.approx(10.0)

    with patch(
        "nonebot_plugin_trade.market.simulate_bar",
        return_value=SimulatedBar(open=10.5, high=10.48, low=10.2, close=10.395),
    ):
        await apply_tick(state, datetime(2026, 11, 19, 9, 0), session)

    assert candle.high == pytest.approx(10.5)
    assert candle.low == pytest.approx(10.0)
    assert candle.close == pytest.approx(10.395)


def test_chart_reference_outside_visible_range_skips_label(monkeypatch: pytest.MonkeyPatch):
    """参考价落到可视区间外时只跳过虚线与标签，不应留下悬浮的画布外数字"""
    from matplotlib.axes import Axes

    from nonebot_plugin_trade.chart import CandlePoint, render_kline_chart

    points = [CandlePoint(day=date(2026, 11, 19), slot=0, open=10.0, high=10.1, low=9.9, close=10.05)]
    labels: list[tuple] = []
    original_text = Axes.text

    def spy_text(self, *args, **kwargs):
        labels.append(args)
        return original_text(self, *args, **kwargs)

    monkeypatch.setattr(Axes, "text", spy_text)

    outside = render_kline_chart(
        date(2026, 11, 19),
        points,
        "test",
        "empty",
        reference_price=99.0,
        visible_candles=8,
    )
    assert outside.startswith(b"\x89PNG\r\n\x1a\n")
    assert labels == []

    labels.clear()
    inside = render_kline_chart(
        date(2026, 11, 19),
        points,
        "test",
        "empty",
        reference_price=10.05,
        visible_candles=8,
    )
    assert inside.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(labels) == 1
