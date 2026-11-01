"""nonebot_plugin_bag 的 /bag usage（alias /bag use）回归测试。

QQ 官方机器人发送 markdown：每条物品的用法用围栏代码块包裹，避免 `<@目标>` 等
尖括号被当成 HTML 标签吞掉；其余平台保持纯文本。二十面骰子用 /roll 消耗，
必须带 usage_command 与本地化的用法说明，否则不会出现在 /bag usage 里。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


def _fake_item(index: int, name: str, count: int, usage_command: str) -> MagicMock:
    item = MagicMock()
    item.index = index
    item.stack.count = count
    item.stack.getName = AsyncMock(return_value=name)
    item.stack.item.usage_command = usage_command
    return item


@pytest.mark.asyncio
async def test_bag_usage_qq_wraps_usage_in_code_block(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Text, UniMessage

    from nonebot_plugin_bag.commands import usage as usage_module

    item = _fake_item(1, "鸡蛋", 5, "splat")
    usage_text = "向指定用户投掷：/splat <@目标> [数量]"

    async def fake_collect(_user_id: str, _index: int | None = None) -> list:
        return [(item, usage_text)]

    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    finish = AsyncMock()
    monkeypatch.setattr(usage_module, "collect_usage_items", fake_collect)
    monkeypatch.setattr(usage_module, "get_command_prefix", lambda: "/")
    monkeypatch.setattr(UniMessage, "send", fake_send)
    monkeypatch.setattr(usage_module.bag, "finish", finish)

    await usage_module._(bot=MagicMock(spec=QQBot), event=MagicMock(), index=None, user_id="usage-user")

    assert len(sent) == 1
    text = next(seg for seg in sent[0] if isinstance(seg, Text))
    assert any("markdown" in styles for styles in text.styles.values())
    # 整条用法被围栏代码块包裹
    assert f"```\n{usage_text}\n```" in text.text
    finish.assert_awaited()


@pytest.mark.asyncio
async def test_bag_usage_other_adapter_keeps_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_alconna.uniseg import UniMessage

    from nonebot_plugin_bag.commands import usage as usage_module

    item = _fake_item(1, "鸡蛋", 5, "splat")

    async def fake_collect(_user_id: str, _index: int | None = None) -> list:
        return [(item, "向指定用户投掷：/splat <@目标> [数量]")]

    send = AsyncMock()
    finish = AsyncMock()
    monkeypatch.setattr(usage_module, "collect_usage_items", fake_collect)
    monkeypatch.setattr(UniMessage, "send", send)
    monkeypatch.setattr(usage_module.bag, "finish", finish)

    await usage_module._(bot=MagicMock(), event=MagicMock(), index=None, user_id="usage-user")

    send.assert_not_awaited()
    plain = finish.await_args.args[0]
    assert "```" not in plain
    assert "[1] 鸡蛋 x5：向指定用户投掷：/splat <@目标> [数量]" in plain


@pytest.mark.asyncio
async def test_dice_has_roll_usage() -> None:
    """二十面骰子通过 /roll 消耗，需要同时有 usage_command 与本地化用法"""
    from nonebot_plugin_items.base.stack import ItemStack
    from nonebot_plugin_items.items.moonlark.dice import Dice
    from nonebot_plugin_items.registry import ITEMS
    from nonebot_plugin_items.registry.registry import ResourceLocation

    dice = ITEMS.getValue(ResourceLocation("moonlark", "dice"))
    assert isinstance(dice, Dice)
    assert dice.usage_command == "roll"

    usage = await dice.getUsageDescription(ItemStack(dice, 1, {}, "dice-user"))
    assert usage is not None
    assert "roll" in usage
