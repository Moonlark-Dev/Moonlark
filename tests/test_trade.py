from datetime import date, datetime
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
    assert first_candle.high >= max(first_candle.open, first_candle.close)
    assert first_candle.low <= min(first_candle.open, first_candle.close)


@pytest.mark.asyncio
async def test_tick_generates_wicks_with_brownian_bridge():
    from nonebot_plugin_trade.market import apply_tick
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    state = make_state(price=10.0, target_minute=720, label1="up", label2="up")

    with (
        patch("nonebot_plugin_trade.market._rand_float", side_effect=[0.0, 1.0]),
        patch("nonebot_plugin_trade.market._rand_normal", return_value=2.0),
    ):
        await apply_tick(state, datetime(2026, 11, 19, 9, 0), session)

    candle = session.objects[(Candle, (TRADE_DAY, 11))]
    assert candle.close == pytest.approx(10.1)
    # 布朗桥在开收盘价之间补出盘中路径，影线会超出实体
    assert candle.high > candle.close
    assert candle.low == pytest.approx(10.0)


def test_brownian_bridge_extremes():
    from nonebot_plugin_trade.market import _brownian_bridge_extremes

    with patch("nonebot_plugin_trade.market._rand_normal", side_effect=[2.0, -2.0] + [0.0] * 13):
        high, low = _brownian_bridge_extremes(10.0, 10.0, 0.005)
    assert high > 10.0
    assert low < 10.0
    # 偏离上限为 3σ√(t(1-t))，不会生成夸张的影线
    assert high - 10.0 <= 3.0 * 0.005 * 10.0 * 0.5 + 1e-9
    assert 10.0 - low <= 3.0 * 0.005 * 10.0 * 0.5 + 1e-9

    # 价格贴近地板价时，布朗桥采样点同样不会低于 0.01
    with patch("nonebot_plugin_trade.market._rand_normal", return_value=-3.0):
        _, low = _brownian_bridge_extremes(0.02, 0.01, 1.0)
    assert low == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_ensure_market_cross_day():
    from nonebot_plugin_trade.market import ensure_market
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    with (
        patch("nonebot_plugin_trade.market._random_target_minute", return_value=720),
        patch("nonebot_plugin_trade.market._random_label", return_value="up"),
        patch("nonebot_plugin_trade.market._random_gap_ratio", return_value=0.02) as gap,
    ):
        state = await ensure_market(session, datetime(2026, 11, 19, 14, 0))
        # 冷启动没有历史收盘价，不制造隔夜跳空
        assert gap.call_count == 0
        assert state.day == TRADE_DAY
        assert state.prev_close == pytest.approx(10.0)
        assert state.day_open == pytest.approx(10.0)
        assert state.last_tick_at == datetime(2026, 11, 19, 14, 0)
        assert len([key for key in session.objects if key[0] is Candle]) == 72
        assert state.price > 0

        await ensure_market(session, datetime(2026, 11, 19, 23, 59))
        assert gap.call_count == 0
        assert state.day == TRADE_DAY
        assert state.last_tick_at == datetime(2026, 11, 19, 23, 55)
        assert len([key for key in session.objects if key[0] is Candle]) == 191
        close_price = state.price

        await ensure_market(session, datetime(2026, 11, 20, 8, 0))
        # 08:00 开市立即跳空一次：今开在昨收基础上跳 2%
        assert gap.call_count == 1
        assert state.day == date(2026, 11, 20)
        # 08:00 的跳空 tick 只更新价格，不写 K 线，缺口保留在昨收与今开之间
        assert state.prev_close == pytest.approx(close_price)
        assert state.day_open == pytest.approx(round(close_price * 1.02, 6))
        assert state.price == pytest.approx(state.day_open)
        assert state.last_tick_at == datetime(2026, 11, 20, 8, 0)
        assert len([key for key in session.objects if key[0] is Candle]) == 191

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
        assert state.price > 0


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
        CandlePoint(day=date(2026, 11, 18), slot=189, open=9.9, high=10.0, low=9.8, close=9.95),
        CandlePoint(day=date(2026, 11, 18), slot=190, open=9.95, high=10.1, low=9.9, close=10.05),
        CandlePoint(day=date(2026, 11, 19), slot=0, open=10.2, high=10.3, low=10.1, close=10.25, volume=10),
    ]
    data = render_kline_chart(date(2026, 11, 19), points, "test", "empty", reference_price=10.2, visible_candles=8)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    empty = render_kline_chart(date(2026, 11, 19), [], "test", "empty")
    assert empty.startswith(b"\x89PNG\r\n\x1a\n")


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
        "/trade buy 100",
        "/trade buy all",
        "/trade sell 100",
        "/trade sell all",
        "/trade",
    ]


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
    """tick 的布朗桥只扩展、不覆盖成交写入的 high/low"""
    from nonebot_plugin_trade.market import apply_tick, update_candle_on_trade
    from nonebot_plugin_trade.models import Candle

    session = FakeSession()
    state = make_state(price=10.5, target_minute=720, label1="up", label2="up")
    await update_candle_on_trade(session, state, datetime(2026, 11, 19, 8, 55), 10.0, 10.5, 100)
    candle = session.objects[(Candle, (TRADE_DAY, 11))]
    assert candle.high == pytest.approx(10.5)
    assert candle.low == pytest.approx(10.0)

    with (
        patch("nonebot_plugin_trade.market._rand_float", side_effect=[0.999, 1.0]),
        patch("nonebot_plugin_trade.market._rand_normal", return_value=-2.0),
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
