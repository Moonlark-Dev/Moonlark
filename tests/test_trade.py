from datetime import date, datetime
from unittest.mock import patch

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


def make_state(**overrides):
    from nonebot_plugin_trade.models import MarketState

    values = {
        "id": 1,
        "price": 10.0,
        "day": TRADE_DAY,
        "day_open": 10.0,
        "prev_close": 10.0,
        "target_minute": 720,
        "label1": "up",
        "label2": "down",
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


def test_segment_and_probability():
    from nonebot_plugin_trade.market import segment_label_and_progress, up_probability

    state = make_state(target_minute=720, label1="up", label2="down")

    label, progress = segment_label_and_progress(state, 540)
    assert label == "up"
    assert progress == pytest.approx((540 - 480) / (720 - 30 - 480))
    assert up_probability(label, progress) == pytest.approx(0.5 + 0.45 * progress)

    label, progress = segment_label_and_progress(state, 720)
    assert label == "flat"
    assert progress == 0.5
    assert up_probability(label, progress) == 0.5

    label, progress = segment_label_and_progress(state, 780)
    assert label == "down"
    assert progress == pytest.approx((780 - 750) / (1440 - 750))
    assert up_probability(label, progress) == pytest.approx(0.5 - 0.45 * progress)

    assert up_probability("up", 0.0) == 0.5
    assert up_probability("up", 1.0) == pytest.approx(0.95)
    assert up_probability("down", 1.0) == pytest.approx(0.05)


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
async def test_tick_price_and_floor():
    from nonebot_plugin_trade.market import apply_tick

    session = FakeSession()
    state = make_state(price=10.0, target_minute=720, label1="up", label2="up")

    with patch("nonebot_plugin_trade.market._rand_float", side_effect=[0.0, 1.0]):
        await apply_tick(state, datetime(2026, 11, 19, 9, 0), session)
    assert state.price == pytest.approx(10.1)

    with patch("nonebot_plugin_trade.market._rand_float", side_effect=[0.999, 1.0]):
        await apply_tick(state, datetime(2026, 11, 19, 9, 5), session)
    assert state.price == pytest.approx(9.999)

    state.price = 0.01
    with patch("nonebot_plugin_trade.market._rand_float", side_effect=[0.999, 1.0]):
        await apply_tick(state, datetime(2026, 11, 19, 9, 10), session)
    assert state.price == 0.01

    from nonebot_plugin_trade.models import Candle

    first_candle = session.objects[(Candle, (TRADE_DAY, 11))]
    assert first_candle.open == pytest.approx(10.0)
    assert first_candle.close == pytest.approx(10.1)


@pytest.mark.asyncio
async def test_ensure_market_cross_day():
    from nonebot_plugin_trade.market import ensure_market
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    with (
        patch("nonebot_plugin_trade.market._random_target_minute", return_value=720),
        patch("nonebot_plugin_trade.market._random_label", return_value="up"),
    ):
        state = await ensure_market(session, datetime(2026, 11, 19, 14, 0))
        assert state.day == TRADE_DAY
        assert state.day_open == pytest.approx(10.0)
        assert state.prev_close == pytest.approx(10.0)
        assert state.last_tick_at == datetime(2026, 11, 19, 14, 0)
        assert len([key for key in session.objects if key[0] is Candle]) == 72
        assert state.price > 0

        await ensure_market(session, datetime(2026, 11, 19, 23, 59))
        assert state.day == TRADE_DAY
        assert state.last_tick_at == datetime(2026, 11, 19, 23, 55)
        assert len([key for key in session.objects if key[0] is Candle]) == 191
        close_price = state.price

        await ensure_market(session, datetime(2026, 11, 20, 8, 0))
        assert state.day == date(2026, 11, 20)
        assert state.day_open == pytest.approx(close_price)
        assert state.prev_close == pytest.approx(close_price)
        assert state.last_tick_at == datetime(2026, 11, 20, 8, 0)


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
    assert state.float_shares == 100000
    assert user.vimcoin == pytest.approx(990.0)

    session = FakeSession()
    session.add(make_holding(shares=100, frozen_shares=0, cost_basis=1010.0, daily_sold=950))
    state = make_state(float_shares=99900)
    user = FakeUser()
    result = await execute_sell(session, state, user, "all", datetime(2026, 11, 19, 10, 0))
    assert result.shares == 50
    assert result.capped_reason == "daily"


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
        CandlePoint(slot=0, open=10.0, high=10.1, low=9.9, close=10.05, volume=10),
        CandlePoint(slot=1, open=10.05, high=10.2, low=10.0, close=10.1, volume=20),
    ]
    data = render_kline_chart(date(2026, 11, 19), points, "test", "empty")
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    empty = render_kline_chart(date(2026, 11, 19), [], "test", "empty")
    assert empty.startswith(b"\x89PNG\r\n\x1a\n")


def test_help_does_not_expose_internal_mechanism():
    from pathlib import Path

    import yaml

    path = Path(__file__).parent.parent / "src" / "lang" / "zh_hans" / "trade.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    details = data["help"]["details"]
    assert "标签" not in details
    assert "目标时间" not in details
    assert "11:00" not in details
    assert "20:00" not in details
