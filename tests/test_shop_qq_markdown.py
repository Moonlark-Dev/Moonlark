"""nonebot_plugin_shop 的 QQ 官方机器人 Markdown 商店回归测试。

QQ 官方机器人下 /shop 使用 markdown 渲染：标题与持有余额、可点击商品条目
（<qqbot-cmd-input>，点击即把 `{前缀}shop buy <编号> 1` 填入输入框）、购买提示。
商品文本只展示名称与单价，编号不出现在 show 属性中；其余平台仍发送纯文本列表。
每个分类自成一个块（块之间空一行），否则分类标题会被解析成上一个列表项的续行。
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

_SHOP_LANG = Path(__file__).parent.parent / "src" / "lang" / "zh_hans" / "shop.yaml"
# 商品名称与跨分类的全局编号一一对应（分类标题出现在新分类的第一件商品之前）
_GOODS_NAMES = [
    "小鱼干",
    "毛线球",
    "铃铛项圈",
    "猫薄荷包",
    "逗猫棒",
    "猫罐头",
    "鸡蛋",
    "二十面骰子",
    "牛奶",
    "临时屏障",
]
_CATEGORY_HEADERS = {1: "【礼物】", 7: "【道具】", 9: "【消耗品】", 10: "【装备】"}


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = str(value)
    return flat


class _FakeUser:
    def __init__(self, vimcoin: float) -> None:
        self._vimcoin = vimcoin

    def get_vimcoin(self) -> float:
        return self._vimcoin


@pytest.fixture
def shop_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """打桩 LangHelper.text（按真实 shop.yaml 模板渲染）与商品名、用户查询。

    注意：插件导入必须在 fixture 内部进行（collection 阶段 nonebot 尚未初始化）。"""
    import nonebot_plugin_shop.__main__ as module
    from nonebot_plugin_larklang.__main__ import LangHelper, remove_trailing_blank_lines

    templates = _flatten(yaml.safe_load(_SHOP_LANG.read_text(encoding="utf-8")))
    item_ids = [item_id for item_id, _ in module.GOODS]

    async def fake_text(_self: LangHelper, key: str, _user_id: str, *args: object) -> str:
        return remove_trailing_blank_lines(templates[key].format(*args, __prefix__="/"))

    async def fake_get_goods_name(item_id: str, _user_id: str) -> str:
        return _GOODS_NAMES[item_ids.index(item_id)]

    async def fake_get_user(_user_id: str) -> _FakeUser:
        return _FakeUser(40399.6)

    monkeypatch.setattr(LangHelper, "text", fake_text)
    monkeypatch.setattr(module, "get_goods_name", fake_get_goods_name)
    monkeypatch.setattr(module, "get_user", fake_get_user)
    return module


def _expected_markdown(goods: list[tuple[str, int]]) -> str:
    blocks: list[str] = []
    current: list[str] = []
    for index, (name, (_, price)) in enumerate(zip(_GOODS_NAMES, goods), start=1):
        if index in _CATEGORY_HEADERS:
            if current:
                blocks.append("\n".join(current))
            current = [_CATEGORY_HEADERS[index]]
        current.append(f'- <qqbot-cmd-input text="/shop buy {index} 1" show="{name} ({price}vi)" reference="false" />')
    if current:
        blocks.append("\n".join(current))
    title = "## 商店\n> 当前持有：40399.6 VimCoin"
    return "\n\n".join([title, *blocks, "点击可以进行购买"])


@pytest.mark.asyncio
async def test_build_markdown_list(shop_env: Any) -> None:
    """markdown 列表：标题/余额引用块 + 可点击商品条目 + 购买提示，编号不出现在商品文本中"""
    markdown = await shop_env.build_markdown_list("10", 40399.6)

    assert markdown == _expected_markdown(shop_env.GOODS)
    # 编号只用于拼装指令，不展示在商品文本里
    assert 'text="/shop buy 1 1"' in markdown
    assert 'show="小鱼干 (20vi)"' in markdown
    assert "【Moonlark 商店】" not in markdown
    # 每个分类标题自成一段，紧跟在上一个分类的列表项后面会带上无序列表缩进
    for header in _CATEGORY_HEADERS.values():
        assert f"\n\n{header}\n" in f"\n{markdown}\n"


@pytest.mark.asyncio
async def test_handle_main_qq_sends_markdown(shop_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人：/shop 发送 markdown 消息，并单独结束处理器"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Text, UniMessage

    module = shop_env
    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    finish = AsyncMock()
    monkeypatch.setattr(UniMessage, "send", fake_send)
    monkeypatch.setattr(module.shop, "finish", finish)

    await module.handle_main(bot=MagicMock(spec=QQBot), user_id="10")

    assert len(sent) == 1
    text = next(seg for seg in sent[0] if isinstance(seg, Text))
    assert any("markdown" in styles for styles in text.styles.values())
    assert text.text == _expected_markdown(module.GOODS)
    finish.assert_awaited()


@pytest.mark.asyncio
async def test_handle_main_other_adapter_sends_plain_text(shop_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """非 QQ 平台：/shop 仍发送纯文本列表，不发送 markdown"""
    from nonebot_plugin_alconna.uniseg import UniMessage

    module = shop_env
    send = AsyncMock()
    finish = AsyncMock()
    monkeypatch.setattr(UniMessage, "send", send)
    monkeypatch.setattr(module.shop, "finish", finish)

    await module.handle_main(bot=MagicMock(), user_id="10")

    send.assert_not_awaited()
    finish.assert_awaited_once()
    plain = finish.await_args.args[0]
    assert plain.splitlines()[0] == "【Moonlark 商店】当前持有：40399.6 VimCoin"
    assert "【礼物】" in plain
    assert "【道具】" in plain
    assert "【消耗品】" in plain
    assert "【装备】" in plain
    assert "[1] 小鱼干 - 20 VimCoin" in plain
    assert "[9] 牛奶 - 35 VimCoin" in plain
    assert "[10] 临时屏障 - 150 VimCoin" in plain
    assert "qqbot-cmd-input" not in plain
