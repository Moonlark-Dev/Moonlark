"""nonebot_plugin_market 的功能回归测试。

覆盖四部分：
1. 上架价格解析（留空按均价、连续 +/- 浮动、固定单价、非法参数）；
2. 基准价来源（优先平均成交价，其次是物品 NBT 的 price）；
3. `market sell` / `market buy` 的背包、VimCoin 与成交记录处理；
4. QQ 官方机器人下 `market list` 的 markdown 渲染（含 <qqbot-cmd-input>
   购买按钮）与其它平台的纯文本列表，以及本地化完整性。
"""

import json
import re
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

_MARKET_DIR = Path(__file__).parent.parent / "src" / "plugins" / "nonebot_plugin_market"
_MARKET_LANG = Path(__file__).parent.parent / "src" / "lang" / "zh_hans" / "market.yaml"
_ITEM_NAMES = {"moonlark:egg": "鸡蛋", "moonlark:dice": "二十面骰子"}


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = str(value)
    return flat


def _templates() -> dict[str, str]:
    return _flatten(yaml.safe_load(_MARKET_LANG.read_text(encoding="utf-8")))


def _listing(
    item_id: int,
    namespace: str = "moonlark:egg",
    count: int = 1,
    price: float = 10.0,
    seller: str = "2",
) -> Any:
    from nonebot_plugin_market.models import MarketItem

    return MarketItem(
        item_id=item_id,
        item_namespace=namespace,
        remain_count=count,
        price=price,
        user_id=seller,
        item_data="{}",
    )


class _FakeItem:
    def __init__(self, location: str) -> None:
        self._location = location

    def getLocation(self) -> str:
        return self._location


class _FakeStack:
    def __init__(self, count: int = 5, data: dict[str, Any] | None = None, namespace: str = "moonlark:egg") -> None:
        self.count = count
        self.data = dict(data or {})
        self.item = _FakeItem(namespace)
        self._name = _ITEM_NAMES.get(namespace, namespace)

    async def getName(self) -> str:
        return self._name

    def getNbt(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class _FakeBagItem:
    def __init__(self, stack: _FakeStack) -> None:
        self.stack = stack
        self.unlocked = 0
        self.saved = 0

    async def unlock_item(self) -> None:
        self.unlocked += 1

    async def on_delete(self) -> None:
        self.saved += 1


class _FakeUser:
    def __init__(self, vimcoin: float = 0.0) -> None:
        self.vimcoin = float(vimcoin)

    def get_vimcoin(self) -> float:
        return self.vimcoin

    async def has_vimcoin(self, count: float) -> bool:
        return self.vimcoin >= count

    async def use_vimcoin(self, count: float) -> bool:
        if self.vimcoin < count:
            return False
        self.vimcoin -= count
        return True

    async def add_vimcoin(self, count: float) -> None:
        self.vimcoin += count


class _FakeScalars:
    def __init__(self, values: list[Any]) -> None:
        self._values = list(values)

    def all(self) -> list[Any]:
        return list(self._values)

    def __iter__(self) -> Any:
        return iter(self._values)


class _FakeSession:
    """最小可用的 AsyncSession 替身：商品列表、按主键查询、成交记录累积"""

    def __init__(self, scalars: list[Any] | None = None, get_results: dict[Any, Any] | None = None) -> None:
        self.scalars_values = list(scalars or [])
        self.get_results = dict(get_results or {})
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.commits = 0
        self.flushes = 0

    async def get(self, model: Any, key: Any) -> Any:
        return self.get_results.get((model, key))

    async def scalars(self, _statement: Any) -> _FakeScalars:
        return _FakeScalars(self.scalars_values)

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if type(obj).__name__ == "SellLog":
            self.get_results[type(obj), obj.item_namespace] = obj

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1


class _SessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _session_factory(session: _FakeSession) -> Any:
    """get_session 替身：所有 session 块复用同一个替身，便于断言写入结果"""

    def factory() -> _SessionContext:
        return _SessionContext(session)

    return factory


def _finished_mock() -> Any:
    """lang.finish / matcher.finish 在真实运行时总会抛出 FinishedException"""

    from nonebot.exception import FinishedException

    return AsyncMock(side_effect=FinishedException)


async def _run(coro: Any) -> None:
    """执行处理器并吞掉终止处理器的 FinishedException"""
    from contextlib import suppress

    from nonebot.exception import FinishedException

    with suppress(FinishedException):
        await coro


class _FakeUniMessage:
    """收集 .style(...).send() 链式调用最终发送的 markdown"""

    sent: ClassVar[list[str]] = []

    def __init__(self) -> None:
        self._text = ""

    def style(self, text: str, _style: str) -> "_FakeUniMessage":
        self._text = text
        return self

    async def send(self, *_args: Any, **_kwargs: Any) -> None:
        type(self).sent.append(self._text)


@pytest.fixture
def market_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """打桩 LangHelper.text（按真实 market.yaml 模板渲染）

    注意：插件导入必须在 fixture 内部进行（collection 阶段 nonebot 尚未初始化）。"""
    import nonebot_plugin_market.__main__ as module
    from nonebot_plugin_larklang.__main__ import LangHelper, remove_trailing_blank_lines

    templates = _templates()

    async def fake_text(_self: LangHelper, key: str, _user_id: str, *args: object) -> str:
        return remove_trailing_blank_lines(templates[key].format(*args, __prefix__="/"))

    monkeypatch.setattr(LangHelper, "text", fake_text)
    _FakeUniMessage.sent.clear()
    return module


def test_alconna_command_arguments(market_env: Any) -> None:
    """命令参数与处理器形参一一对应：sell/buy/list 均可解析，默认值正确"""
    command = market_env.matcher.command()

    sell = command.parse("/market sell 3 5 +++")
    assert sell.matched
    assert sell.subcommands["sell"].args == {"bag_index": 3, "count": 5, "price": "+++"}

    # count 留空表示全部，price 留空表示按均价
    sell = command.parse("/market sell 1")
    assert sell.subcommands["sell"].args == {"bag_index": 1, "count": 0, "price": ""}

    buy = command.parse("/market buy 鸡蛋 2")
    assert buy.subcommands["buy"].args == {"name": "鸡蛋", "count": 2}
    assert command.parse("/market buy 7").subcommands["buy"].args == {"name": "7", "count": 1}

    assert command.parse("/market list").subcommands["list"].args == {"page": 1}
    assert command.parse("/market list 2").subcommands["list"].args == {"page": 2}
    assert command.parse("/market").matched


def test_resolve_unit_price_without_price_argument() -> None:
    """留空时使用基准价；没有基准价时返回 None（由调用方提示填写固定单价）"""
    from nonebot_plugin_market.__main__ import resolve_unit_price

    assert resolve_unit_price("", 100.0) == pytest.approx(100.0)
    assert resolve_unit_price("   ", 12.34) == pytest.approx(12.34)
    assert resolve_unit_price("", None) is None


def test_resolve_unit_price_with_signs() -> None:
    """连续的 +/- 相对基准价浮动 1% × 符号数量，最多 5 个符号"""
    from nonebot_plugin_market.__main__ import resolve_unit_price

    assert resolve_unit_price("+", 100.0) == pytest.approx(101.0)
    assert resolve_unit_price("+++", 100.0) == pytest.approx(103.0)
    assert resolve_unit_price("--", 100.0) == pytest.approx(98.0)
    assert resolve_unit_price("-------", 100.0) == pytest.approx(95.0)
    # 没有基准价（既无成交记录也没有 NBT price）时无法按浮动价上架
    assert resolve_unit_price("+", None) is None


def test_resolve_unit_price_with_fixed_price() -> None:
    """填写数字时作为固定单价，用于还没有成交记录的物品"""
    from nonebot_plugin_market.__main__ import resolve_unit_price

    assert resolve_unit_price("250", None) == pytest.approx(250.0)
    assert resolve_unit_price(" 12.345 ", 100.0) == pytest.approx(12.35)


@pytest.mark.parametrize("price", ["abc", "0", "-5", "+-", "1.2.3", "++a"])
def test_resolve_unit_price_rejects_invalid_argument(price: str) -> None:
    """既不是连续符号也不是正数的参数应报错"""
    from nonebot_plugin_market.__main__ import resolve_unit_price

    with pytest.raises(ValueError, match=r"invalid price|price must be positive"):
        resolve_unit_price(price, 100.0)


@pytest.mark.asyncio
async def test_get_average_price_prefers_sell_log(market_env: Any) -> None:
    """有成交记录时使用平均成交价，忽略物品 NBT 中的 price"""
    from nonebot_plugin_market.models import SellLog

    module = market_env
    log = SellLog(item_namespace="moonlark:egg", sold_count=4, price_sum=60)
    session = _FakeSession(get_results={(SellLog, "moonlark:egg"): log})

    assert await module.get_average_price(_FakeStack(data={"price": 999}), session) == pytest.approx(15.0)


@pytest.mark.asyncio
async def test_get_average_price_falls_back_to_nbt(market_env: Any) -> None:
    """没有成交记录时退回 NBT price；非法或非正数的 price 视为不可出售"""
    module = market_env
    session = _FakeSession()

    assert await module.get_average_price(_FakeStack(data={"price": 20}), session) == pytest.approx(20.0)
    assert await module.get_average_price(_FakeStack(data={}), session) is None
    assert await module.get_average_price(_FakeStack(data={"price": "abc"}), session) is None
    assert await module.get_average_price(_FakeStack(data={"price": 0}), session) is None


@pytest.mark.asyncio
async def test_build_markdown_list(market_env: Any) -> None:
    """markdown 列表：标题/页码 + 可点击购买条目 + 翻页提示，编号取自 item_id"""
    module = market_env
    items = [
        (_listing(3, count=5, price=15.0), "鸡蛋"),
        (_listing(4, namespace="moonlark:dice", price=30.0), "二十面骰子"),
    ]

    markdown = await module.build_markdown_list("10", 1, 2, 12, items)

    assert markdown == "\n".join(
        [
            "## 全球市场",
            "> 第 1/2 页 · 共 12 件商品在售",
            "",
            '- <qqbot-cmd-input text="/market buy 3 1" show="鸡蛋 ×5 · 15.0 VimCoin" reference="false" />',
            '- <qqbot-cmd-input text="/market buy 4 1" show="二十面骰子 ×1 · 30.0 VimCoin" reference="false" />',
            "",
            "点击商品即可购买，使用 /market list 页码 翻页",
        ],
    )


@pytest.mark.asyncio
async def test_handle_market_list_qq_sends_markdown(market_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人：market list 发送带购买按钮的 markdown，并单独结束处理器"""
    from nonebot.adapters.qq import Bot as QQBot

    module = market_env
    session = _FakeSession(
        scalars=[_listing(1, count=5, price=15.0), _listing(2, namespace="moonlark:dice", price=30.0)],
    )

    async def fake_get_market_item(_user_id: str, data: Any) -> _FakeStack:
        return _FakeStack(count=data.remain_count, namespace=data.item_namespace)

    finish = _finished_mock()
    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module, "get_market_item", fake_get_market_item)
    monkeypatch.setattr(module, "UniMessage", _FakeUniMessage)
    monkeypatch.setattr(module.matcher, "finish", finish)

    await _run(module.handle_market_list(bot=MagicMock(spec=QQBot), page=1, user_id="10"))

    assert len(_FakeUniMessage.sent) == 1
    markdown = _FakeUniMessage.sent[0]
    assert markdown.startswith("## 全球市场")
    assert '<qqbot-cmd-input text="/market buy 1 1" show="鸡蛋 ×5 · 15.0 VimCoin" reference="false" />' in markdown
    assert (
        '<qqbot-cmd-input text="/market buy 2 1" show="二十面骰子 ×1 · 30.0 VimCoin" reference="false" />' in markdown
    )
    finish.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_handle_market_list_other_adapter_sends_plain_text(
    market_env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 QQ 平台：market list 发送纯文本列表，不发送 markdown"""

    module = market_env
    session = _FakeSession(scalars=[_listing(1, count=5, price=15.0)])

    async def fake_get_market_item(_user_id: str, data: Any) -> _FakeStack:
        return _FakeStack(count=data.remain_count, namespace=data.item_namespace)

    finish = _finished_mock()
    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module, "get_market_item", fake_get_market_item)
    monkeypatch.setattr(module, "UniMessage", _FakeUniMessage)
    monkeypatch.setattr(module.matcher, "finish", finish)

    await _run(module.handle_market_list(bot=MagicMock(), page=1, user_id="10"))

    assert _FakeUniMessage.sent == []
    finish.assert_awaited_once()
    plain = finish.await_args.args[0]
    assert plain.splitlines()[0] == "📦 全球市场（第 1/1 页，共 1 件）"
    assert "1. 鸡蛋 ×5 — 15.0 VimCoin" in plain
    assert "qqbot-cmd-input" not in plain


@pytest.mark.asyncio
async def test_find_market_items_by_id_and_name(market_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """纯数字按商品编号精确匹配，其它关键词按物品名称模糊匹配"""
    from nonebot_plugin_market.models import MarketItem

    module = market_env
    egg, dice = _listing(7, count=2), _listing(8, namespace="moonlark:dice", count=0)

    assert await module.find_market_items("1", _FakeSession(get_results={(MarketItem, 7): egg}), " 7 ") == [egg]
    # 已售罄的记录即使编号存在也不可购买
    assert await module.find_market_items("1", _FakeSession(get_results={(MarketItem, 8): dice}), "8") == []

    listings = [_listing(1), _listing(2, namespace="moonlark:dice")]

    async def fake_get_market_item(_user_id: str, data: Any) -> _FakeStack:
        return _FakeStack(namespace=data.item_namespace)

    monkeypatch.setattr(module, "get_market_item", fake_get_market_item)
    assert await module.find_market_items("1", _FakeSession(scalars=listings), "鸡") == [listings[0]]
    assert await module.find_market_items("1", _FakeSession(scalars=listings), "不存在") == []


@pytest.mark.asyncio
async def test_handle_market_sell_lists_item_and_consumes_bag(market_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """上架成功：写入上架记录（JSON 文本）、从背包扣除物品并结束处理器"""

    module = market_env
    stack = _FakeStack(count=5, data={"price": 100})
    bag_item = _FakeBagItem(stack)
    session = _FakeSession()

    async def fake_get_bag_item(_user_id: str, _index: int) -> _FakeBagItem:
        return bag_item

    finish = _finished_mock()
    monkeypatch.setattr(module, "get_bag_item", fake_get_bag_item)
    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module.lang, "finish", finish)

    await _run(module.handle_market_sell(bag_index=1, count=3, price="+++", user_id="10"))

    assert len(session.added) == 1
    listing = session.added[0]
    assert listing.user_id == "10"
    assert listing.item_namespace == "moonlark:egg"
    assert listing.remain_count == 3
    assert listing.price == pytest.approx(103.0)
    # 新写法：物品 NBT 以 JSON 文本保存，而不是 BLOB
    assert listing.item_data == json.dumps({"price": 100})
    assert isinstance(listing.item_data, str)
    assert session.commits == 1
    assert stack.count == 2
    assert bag_item.saved == 1
    assert bag_item.unlocked == 0
    finish.assert_awaited_once_with("sell.done", "10", 3, "鸡蛋", 103.0)


@pytest.mark.asyncio
async def test_handle_market_sell_fixed_price_without_sell_log(
    market_env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有成交记录时可以直接填写固定单价上架"""

    module = market_env
    bag_item = _FakeBagItem(_FakeStack(count=1, data={}))
    session = _FakeSession()

    async def fake_get_bag_item(_user_id: str, _index: int) -> _FakeBagItem:
        return bag_item

    finish = _finished_mock()
    monkeypatch.setattr(module, "get_bag_item", fake_get_bag_item)
    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module.lang, "finish", finish)

    await _run(module.handle_market_sell(bag_index=1, count=0, price="250", user_id="10"))

    assert session.added[0].price == pytest.approx(250.0)
    assert session.added[0].remain_count == 1
    finish.assert_awaited_once_with("sell.done", "10", 1, "鸡蛋", 250.0)


@pytest.mark.asyncio
async def test_handle_market_sell_unlocks_item_on_failure(market_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """校验失败时必须解锁并保留背包物品，不能留下上架记录"""

    module = market_env
    stack = _FakeStack(count=5, data={"price": 100})
    bag_item = _FakeBagItem(stack)
    session = _FakeSession()
    finish = _finished_mock()

    async def fake_get_bag_item(_user_id: str, _index: int) -> _FakeBagItem:
        return bag_item

    monkeypatch.setattr(module, "get_bag_item", fake_get_bag_item)
    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module.lang, "finish", finish)

    await _run(module.handle_market_sell(bag_index=1, count=1, price="abc", user_id="10"))
    assert bag_item.unlocked == 1
    finish.assert_awaited_once_with("sell.wrong_price", "10")

    bag_item.unlocked = 0
    await _run(module.handle_market_sell(bag_index=1, count=9, price="", user_id="10"))
    assert bag_item.unlocked == 1
    assert finish.await_args.args == ("sell.item_not_enough", "10", 5)

    bag_item.unlocked = 0
    await _run(module.handle_market_sell(bag_index=1, count=-1, price="", user_id="10"))
    assert bag_item.unlocked == 1
    assert finish.await_args.args == ("sell.wrong_count", "10")

    assert session.added == []
    assert stack.count == 5


@pytest.mark.asyncio
async def test_handle_market_sell_asks_fixed_price_without_any_base(
    market_env: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """既无成交记录也没有 NBT price 时提示填写固定单价"""

    module = market_env
    bag_item = _FakeBagItem(_FakeStack(count=2, data={}))
    session = _FakeSession()
    finish = _finished_mock()

    async def fake_get_bag_item(_user_id: str, _index: int) -> _FakeBagItem:
        return bag_item

    monkeypatch.setattr(module, "get_bag_item", fake_get_bag_item)
    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module.lang, "finish", finish)

    await _run(module.handle_market_sell(bag_index=1, count=1, price="+", user_id="10"))

    assert bag_item.unlocked == 1
    assert session.added == []
    finish.assert_awaited_once_with("sell.no_base_price", "10")


@pytest.mark.asyncio
async def test_handle_market_buy_pays_seller_and_records_sell(market_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """购买：按需跨多条上架记录买入、扣除买家 VimCoin、卖家收 99%、累计成交记录"""
    from nonebot_plugin_market.models import SellLog

    module = market_env
    listings = [_listing(1, count=3, price=10.0, seller="2"), _listing(2, count=5, price=10.0, seller="3")]
    session = _FakeSession(scalars=listings)
    users = {"1": _FakeUser(100), "2": _FakeUser(0), "3": _FakeUser(0)}
    given: list[tuple[int, int, str]] = []
    finish = _finished_mock()

    async def fake_get_user(user_id: str) -> _FakeUser:
        return users[user_id]

    async def fake_get_market_item(_user_id: str, data: Any) -> _FakeStack:
        return _FakeStack(count=data.remain_count, namespace=data.item_namespace)

    async def fake_give_market_item(count: int, data: Any, user_id: str) -> None:
        given.append((count, data.item_id, user_id))

    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module, "get_user", fake_get_user)
    monkeypatch.setattr(module, "get_market_item", fake_get_market_item)
    monkeypatch.setattr(module, "give_market_item", fake_give_market_item)
    monkeypatch.setattr(module.lang, "finish", finish)

    await _run(module.handle_market_buy(name="鸡蛋", count=6, user_id="1"))

    assert given == [(3, 1, "1"), (3, 2, "1")]
    assert users["1"].get_vimcoin() == pytest.approx(40.0)
    assert users["2"].get_vimcoin() == pytest.approx(29.7)
    assert users["3"].get_vimcoin() == pytest.approx(29.7)
    log = session.get_results[SellLog, "moonlark:egg"]
    assert log.sold_count == 6
    assert log.price_sum == pytest.approx(60.0)
    # 第一条上架记录已售罄并删除，第二条剩余 2 个
    assert session.deleted == [listings[0]]
    assert listings[1].remain_count == 2
    assert session.commits == 1
    finish.assert_awaited_once_with("buy.finish", "1", 6, "鸡蛋", 60.0)


@pytest.mark.asyncio
async def test_handle_market_buy_rejects_invalid_count(market_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """购买数量必须为正数"""

    module = market_env
    finish = _finished_mock()
    monkeypatch.setattr(module.lang, "finish", finish)

    await _run(module.handle_market_buy(name="鸡蛋", count=0, user_id="1"))

    finish.assert_awaited_once_with("buy.wrong_count", "1")


@pytest.mark.asyncio
async def test_handle_market_buy_reports_missing_item(market_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """没有匹配的在售商品时提示未找到"""

    module = market_env
    session = _FakeSession(scalars=[])
    finish = _finished_mock()
    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=_FakeUser(100)))
    monkeypatch.setattr(module.lang, "finish", finish)

    await _run(module.handle_market_buy(name="不存在", count=1, user_id="1"))

    assert session.commits == 0
    finish.assert_awaited_once_with("buy.not_found", "1", "不存在")


@pytest.mark.asyncio
async def test_handle_market_buy_reports_not_enough_vimcoin(market_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """VimCoin 不足时不扣款、不发货"""

    module = market_env
    listings = [_listing(1, count=2, price=10.0, seller="2")]
    session = _FakeSession(scalars=listings)
    buyer = _FakeUser(5)
    finish = _finished_mock()
    given: list[Any] = []

    async def fake_get_market_item(_user_id: str, data: Any) -> _FakeStack:
        return _FakeStack(count=data.remain_count, namespace=data.item_namespace)

    monkeypatch.setattr(module, "get_session", _session_factory(session))
    monkeypatch.setattr(module, "get_user", AsyncMock(return_value=buyer))
    monkeypatch.setattr(module, "get_market_item", fake_get_market_item)
    monkeypatch.setattr(module, "give_market_item", AsyncMock(side_effect=lambda *a: given.append(a)))
    monkeypatch.setattr(module.lang, "finish", finish)

    await _run(module.handle_market_buy(name="鸡蛋", count=1, user_id="1"))

    assert buyer.get_vimcoin() == 5
    assert given == []
    assert listings[0].remain_count == 2
    finish.assert_awaited_once_with("buy.no_enough_vimcoin", "1")


def test_localization_keys_are_complete() -> None:
    """larklang 本地化文件必须包含代码引用的所有键，且帮助用法格式统一"""
    templates = _templates()
    source = (_MARKET_DIR / "__main__.py").read_text(encoding="utf-8")
    referenced = set(re.findall(r'lang\.(?:text|finish|send)\(\s*"([^"]+)"', source))

    assert referenced, "未能从源码中提取到任何本地化键"
    assert referenced <= set(templates), f"缺少本地化键: {sorted(referenced - set(templates))}"

    help_data = yaml.safe_load((_MARKET_DIR / "help.yaml").read_text(encoding="utf-8"))
    usages = help_data["commands"]["market"]["usages"]
    assert usages == [f"help.usage{i}" for i in range(1, len(usages) + 1)]
    for key in usages:
        usage = templates[key]
        assert usage.startswith("market "), usage
        # 用法格式：指令名 <子命令> <args...> (说明)，说明使用半角括号
        assert re.search(r"\([^()]+\)$", usage), usage
        assert "—" not in usage
