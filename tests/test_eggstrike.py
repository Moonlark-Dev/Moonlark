from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml


@pytest.mark.asyncio
async def test_get_start_datetime() -> None:
    from nonebot_plugin_eggstrike.__main__ import get_start_datetime

    assert get_start_datetime("7d") is not None
    assert get_start_datetime("30d") is not None
    assert get_start_datetime("total") is None


@pytest.mark.asyncio
async def test_attack_record_queries() -> None:
    from nonebot_plugin_eggstrike.__main__ import build_ranking, get_start_datetime, max_count, sum_count
    from nonebot_plugin_eggstrike.models import AttackRecord
    from nonebot_plugin_orm import get_session

    now = datetime.now()
    async with get_session() as session:
        session.add(AttackRecord(user_id="u1", target_id="t1", count=5, egg_id="moonlark:egg", time=now))
        session.add(
            AttackRecord(user_id="u1", target_id="t1", count=3, egg_id="moonlark:egg", time=now - timedelta(days=10)),
        )
        session.add(AttackRecord(user_id="u2", target_id="t1", count=2, egg_id="moonlark:egg", time=now))
        session.add(AttackRecord(user_id="u2", target_id="t2", count=8, egg_id="moonlark:egg", time=now))
        await session.commit()

    assert await sum_count(AttackRecord.target_id, "t1", get_start_datetime("7d")) == 7
    assert await sum_count(AttackRecord.target_id, "t1", None) == 10
    assert await sum_count(AttackRecord.user_id, "u2", None) == 10
    assert await max_count(AttackRecord.user_id, "u1", None) == 5
    assert await max_count(AttackRecord.target_id, "t2", None) == 8

    rows = await build_ranking(AttackRecord.target_id, "total")
    assert rows[0].target_id == "t1"
    assert rows[0].total_count == 10

    rows = await build_ranking(AttackRecord.user_id, "7d")
    assert rows[0].user_id == "u2"
    assert rows[0].total_count == 10


@pytest.mark.asyncio
async def test_egg_item_properties() -> None:
    from nonebot_plugin_items.registry import ITEMS
    from nonebot_plugin_items.registry.registry import ResourceLocation

    location = ResourceLocation("moonlark", "egg")
    egg = ITEMS.getValue(location)
    assert egg.getProperties()["star"] == 1
    assert egg.getProperties()["useable"] is False


@pytest.mark.asyncio
async def test_shop_goods_contains_egg() -> None:
    from nonebot_plugin_shop.goods import GOODS

    assert any(item_id == "moonlark:egg" for item_id, _ in GOODS)


@pytest.mark.asyncio
async def test_consume_eggs() -> None:
    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_items.utils.string import get_location_by_id
    from nonebot_plugin_orm import get_session

    from nonebot_plugin_eggstrike.utils import NotEnoughEggs, deduct_eggs, get_egg_count

    async with get_session() as session:
        session.add(Bag(user_id="consumer1", item_id="moonlark:egg", count=10, bag_index=1, data="{}", locked=False))
        session.add(Bag(user_id="consumer1", item_id="moonlark:egg", count=5, bag_index=2, data="{}", locked=False))
        await session.commit()

    egg_location = get_location_by_id("moonlark:egg")
    assert await get_egg_count("consumer1", egg_location) == 15
    async with get_session() as session:
        await deduct_eggs(session, "consumer1", egg_location, 12)
        await session.commit()
    assert await get_egg_count("consumer1", egg_location) == 3
    with pytest.raises(NotEnoughEggs):
        async with get_session() as session:
            await deduct_eggs(session, "consumer1", egg_location, 100)
    assert await get_egg_count("consumer1", egg_location) == 3


@pytest.mark.asyncio
async def test_deduct_eggs_rolls_back_partial_on_shortage() -> None:
    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_items.utils.string import get_location_by_id
    from nonebot_plugin_orm import get_session

    from nonebot_plugin_eggstrike.utils import NotEnoughEggs, deduct_eggs, get_egg_count

    async with get_session() as session:
        session.add(Bag(user_id="consumer2", item_id="moonlark:egg", count=7, bag_index=1, data="{}", locked=False))
        await session.commit()

    egg_location = get_location_by_id("moonlark:egg")
    with pytest.raises(NotEnoughEggs):
        async with get_session() as session:
            await deduct_eggs(session, "consumer2", egg_location, 10)
    assert await get_egg_count("consumer2", egg_location) == 7


_EGGSTRIKE_LANG = Path(__file__).parent.parent / "src" / "lang" / "zh_hans" / "eggstrike.yaml"

_EGG_NAMES = {"egg": "鸡蛋", "rotten_egg": "臭鸡蛋", "rotten_egg_ex": "臭鸡蛋 Ex"}


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{path}."))
        else:
            flat[path] = str(value)
    return flat


@pytest.fixture
def egg_list_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """按真实 eggstrike.yaml 渲染文案，命令前缀固定为 `/`，并打桩鸡蛋名称与持有数量"""
    import nonebot_plugin_eggstrike.__main__ as module
    from nonebot_plugin_larklang.__main__ import LangHelper, remove_trailing_blank_lines

    templates = _flatten(yaml.safe_load(_EGGSTRIKE_LANG.read_text(encoding="utf-8")))

    async def fake_text(_self: LangHelper, key: str, _user_id: str, *args: object) -> str:
        # 与 LarkLang 的 get_text 一致：占位符数量不匹配时返回未格式化的原文，
        # 让「文案占位符与调用参数对不上」在测试里直接暴露出来
        try:
            text = templates[key].format(*args, __prefix__="/")
        except IndexError:
            text = templates[key]
        return remove_trailing_blank_lines(text)

    async def fake_egg_name(egg_key: str, _user_id: str) -> str:
        return _EGG_NAMES[egg_key]

    monkeypatch.setattr(LangHelper, "text", fake_text)
    monkeypatch.setattr(module, "get_egg_type_name", fake_egg_name)
    monkeypatch.setattr(module, "get_selected_egg_type", AsyncMock(return_value="egg"))
    # 鸡蛋 20 个、臭鸡蛋与臭鸡蛋 Ex 各 0 个
    monkeypatch.setattr(module, "get_egg_count", AsyncMock(side_effect=[20, 0, 0]))
    return module


@pytest.mark.asyncio
async def test_build_eggs_text_shows_counts(egg_list_env: Any) -> None:
    """非 QQ 平台：纯文本鸡蛋列表展示编号、持有数量、当前选择、效果与切换提示"""
    text = await egg_list_env.build_eggs_text("eggs-user")

    assert text.startswith("【鸡蛋列表】当前选择：鸡蛋")
    assert "[1] 鸡蛋 x20（当前使用）" in text
    assert "[2] 臭鸡蛋 x0" in text
    assert "[3] 臭鸡蛋 Ex x0" in text
    assert "每个造成 0.2 点伤害" in text
    assert "恶臭 2 小时" in text
    assert text.endswith("使用 /splat switch <数字> 切换默认鸡蛋")
    assert "qqbot-cmd-input" not in text


@pytest.mark.asyncio
async def test_build_eggs_markdown_is_clickable(egg_list_env: Any) -> None:
    """QQ 官方机器人：鸡蛋列表渲染为 markdown，鸡蛋名是填入 /splat switch 的 <qqbot-cmd-input>"""
    markdown = await egg_list_env.build_eggs_markdown("eggs-user")

    assert markdown.startswith("## 鸡蛋列表")
    assert "> 当前选择：鸡蛋" in markdown
    assert '<qqbot-cmd-input text="/splat switch 1" show="鸡蛋" reference="false" /> x20（当前使用）' in markdown
    assert '<qqbot-cmd-input text="/splat switch 3" show="臭鸡蛋 Ex" reference="false" /> x0' in markdown
    assert "  每个造成 0.2 点伤害" in markdown


@pytest.mark.asyncio
async def test_send_egg_list_qq_uses_clickable_markdown(egg_list_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人下 /splat（不带参数）发送可点击的 markdown 消息"""
    from nonebot.adapters.qq import Bot as QQBot

    module = egg_list_env
    sent: list[str] = []

    class _FakeUniMessage:
        def style(self, text: str, _style: str) -> "_FakeUniMessage":
            sent.append(text)
            return self

        async def send(self, *_args: object, **_kwargs: object) -> None:
            return None

    finish = AsyncMock()
    monkeypatch.setattr(module, "UniMessage", _FakeUniMessage)
    monkeypatch.setattr(module.splat, "finish", finish)

    await module.send_egg_list(MagicMock(spec=QQBot), MagicMock(), "eggs-user")

    assert len(sent) == 1 and "qqbot-cmd-input" in sent[0]
    finish.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_send_egg_list_other_platform_uses_text(egg_list_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """其它适配器没有 cmd-input 渲染能力，发送纯文本列表"""
    module = egg_list_env
    finish = AsyncMock()
    monkeypatch.setattr(module.splat, "finish", finish)

    await module.send_egg_list(MagicMock(), MagicMock(), "eggs-user")

    finish.assert_awaited_once()
    text = finish.await_args.args[0]
    assert "[1] 鸡蛋 x20（当前使用）" in text
    assert "qqbot-cmd-input" not in text
