from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeUser:
    """模拟 larkuser 中只有 VimCoin 交互的用户"""

    def __init__(self, vimcoin: float = 1000.0) -> None:
        self.vimcoin = vimcoin

    async def has_vimcoin(self, count: float) -> bool:
        return self.vimcoin >= count

    async def use_vimcoin(self, count: float) -> bool:
        if not await self.has_vimcoin(count):
            return False
        self.vimcoin -= count
        return True

    async def add_vimcoin(self, count: float) -> None:
        self.vimcoin += count

    def get_vimcoin(self) -> float:
        return self.vimcoin


@pytest.fixture
def fake_user(monkeypatch: pytest.MonkeyPatch) -> _FakeUser:
    import nonebot_plugin_larkuser

    user = _FakeUser()

    async def fake_get_user(_user_id: str, *, writable: bool = False):
        return user

    monkeypatch.setattr(nonebot_plugin_larkuser, "get_user", fake_get_user)
    return user


@pytest.mark.asyncio
async def test_recipes_and_levels() -> None:
    from nonebot_plugin_craft.recipes import LEVEL_SLOTS, MAX_LEVEL, RECIPES

    assert LEVEL_SLOTS == {1: 2, 2: 4, 3: 6, 4: 10}
    assert MAX_LEVEL == 4
    assert RECIPES["rotten_egg"].inputs == {"moonlark:egg": 1}
    assert RECIPES["rotten_egg"].vimcoin == 10
    assert RECIPES["rotten_egg"].duration == timedelta(hours=6)
    assert RECIPES["rotten_egg"].output_id == "moonlark:rotten_egg"
    assert RECIPES["rotten_egg_ex"].duration == timedelta(hours=3)
    assert RECIPES["cake"].inputs == {"moonlark:egg": 5, "moonlark:milk": 3}
    assert RECIPES["cake"].duration == timedelta(hours=24)


@pytest.mark.asyncio
async def test_machine_default_and_slots() -> None:
    from nonebot_plugin_craft.utils import get_machine, get_slots_info

    machine = await get_machine("crafter1")
    assert machine.level == 1
    total, used = await get_slots_info("crafter1")
    assert (total, used) == (2, 0)


@pytest.mark.asyncio
async def test_start_job_deducts_materials_and_slots(fake_user: _FakeUser) -> None:
    from nonebot_plugin_orm import get_session

    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_craft.recipes import RECIPES
    from nonebot_plugin_craft.utils import get_slots_info, start_job

    async def add_bag(user_id: str, item_id: str, count: int) -> None:
        async with get_session() as session:
            session.add(Bag(user_id=user_id, item_id=item_id, count=count, bag_index=1, data="{}", locked=False))
            await session.commit()

    # 材料不足时不扣 VimCoin，也不创建任务
    with pytest.raises(Exception):
        await start_job("crafter2", RECIPES["rotten_egg"])
    assert fake_user.vimcoin == 1000.0

    await add_bag("crafter2", "moonlark:egg", 3)
    job = await start_job("crafter2", RECIPES["rotten_egg"])
    assert job.recipe_id == "rotten_egg"
    # 1 个鸡蛋 + 10 VimCoin
    assert fake_user.vimcoin == 990.0
    total, used = await get_slots_info("crafter2")
    assert used == 1
    assert total == 2


@pytest.mark.asyncio
async def test_start_job_slot_limit(fake_user: _FakeUser) -> None:
    from nonebot_plugin_orm import get_session
    from sqlalchemy import select, func

    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_craft.recipes import RECIPES
    from nonebot_plugin_craft.models import CraftingJob
    from nonebot_plugin_craft.utils import NoFreeSlot, get_slots_info, start_job

    async with get_session() as session:
        session.add(
            Bag(
                user_id="crafter3",
                item_id="moonlark:egg",
                count=10,
                bag_index=1,
                data="{}",
                locked=False,
            )
        )
        await session.commit()

    # 等级 1 只有 2 个槽位
    await start_job("crafter3", RECIPES["rotten_egg"])
    await start_job("crafter3", RECIPES["rotten_egg"])
    with pytest.raises(NoFreeSlot):
        await start_job("crafter3", RECIPES["rotten_egg"])
    total, used = await get_slots_info("crafter3")
    assert (total, used) == (2, 2)
    async with get_session() as session:
        count = await session.scalar(
            select(func.count()).select_from(CraftingJob).where(CraftingJob.user_id == "crafter3")
        )
        assert count == 2


@pytest.mark.asyncio
async def test_collect_finished_jobs_delivers_output(fake_user: _FakeUser) -> None:
    from datetime import datetime

    from nonebot_plugin_orm import get_session
    from sqlalchemy import select

    from nonebot_plugin_bag.models import Bag
    from nonebot_plugin_craft.models import CraftingJob
    from nonebot_plugin_craft.recipes import RECIPES

    from nonebot_plugin_craft.utils import collect_finished_jobs, start_job

    async with get_session() as session:
        session.add(
            Bag(
                user_id="crafter4",
                item_id="moonlark:egg",
                count=5,
                bag_index=1,
                data="{}",
                locked=False,
            )
        )
        await session.commit()

    job = await start_job("crafter4", RECIPES["rotten_egg"])

    # 还没到时间，不能领取
    assert await collect_finished_jobs("crafter4") == []

    # 时间到点后可领取，产物发给用户
    async with get_session() as session:
        row = await session.get(CraftingJob, job.id_)
        row.finish_time = datetime.now() - timedelta(minutes=1)
        await session.commit()

    deliveries = await collect_finished_jobs("crafter4")
    assert deliveries == [(RECIPES["rotten_egg"], 1)]

    async with get_session() as session:
        rotten = (
            await session.scalars(select(Bag).where(Bag.user_id == "crafter4", Bag.item_id == "moonlark:rotten_egg"))
        ).all()
        assert sum(row.count for row in rotten) == 1


@pytest.mark.asyncio
async def test_upgrade_costs(fake_user: _FakeUser) -> None:
    from nonebot_plugin_craft.recipes import LEVEL_SLOTS
    from nonebot_plugin_craft.utils import get_machine, get_upgrade_cost, try_upgrade

    assert get_upgrade_cost(1) == 300
    assert get_upgrade_cost(4) is None

    level, cost, slots = await try_upgrade("upgrader1")
    assert (level, cost, slots) == (2, 300, LEVEL_SLOTS[2])
    assert fake_user.vimcoin == 700.0
    machine = await get_machine("upgrader1")
    assert machine.level == 2

    # 再次升级时 VimCoin 不足会抛异常
    from nonebot_plugin_craft.utils import NotEnoughVimcoin

    fake_user.vimcoin = 100.0
    with pytest.raises(NotEnoughVimcoin):
        await try_upgrade("upgrader1")


@pytest.mark.asyncio
async def test_format_item_list_awaits_each_item_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """回归：名称需要在循环里逐项 await，不能用含 await 的生成器表达式拼字符串。

    含 ``await`` 的生成器表达式会被编译成异步生成器，``str.join`` 收到它只会抛
    ``TypeError: can only join an iterable``；这个异常此前会让 ``/craft`` 的主菜单
    什么都不回。
    """
    from nonebot_plugin_craft import utils

    async def fake_get_item_name(item_id: str, user_id: str) -> str:
        return f"{item_id}-{user_id}"

    monkeypatch.setattr(utils, "get_item_name", fake_get_item_name)
    assert await utils.format_item_list([("egg", 2), ("milk", 1)], "crafter1") == "egg-crafter1x2、milk-crafter1x1"
    assert await utils.format_item_list([], "crafter1") == ""


@pytest.fixture
def panel_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    """把物品名与指令前缀固定下来，让面板断言不依赖物品库与运行配置"""
    from nonebot_plugin_craft import panel
    from nonebot_plugin_craft import utils as craft_utils
    from nonebot_plugin_larkutils.command import config as command_config

    monkeypatch.setattr(command_config, "command_start", ["/"])

    names = {
        "moonlark:egg": "鸡蛋",
        "moonlark:milk": "牛奶",
        "moonlark:rotten_egg": "臭鸡蛋",
        "moonlark:rotten_egg_ex": "精华臭鸡蛋",
        "moonlark:cake": "蛋糕",
    }

    async def fake_get_item_name(item_id: str, _user_id: str) -> str:
        return names.get(item_id, item_id)

    monkeypatch.setattr(panel, "get_item_name", fake_get_item_name)
    monkeypatch.setattr(craft_utils, "get_item_name", fake_get_item_name)


@pytest.mark.asyncio
async def test_panel_markdown_for_qq_has_hierarchy_and_cmd_input(panel_texts: None) -> None:
    """QQ 官方机器人：标题 / 状态 / 分组用 markdown 拉开层次，配方下带 cmd-input"""
    from nonebot_plugin_craft.panel import PanelData, PanelJob, build_panel_markdown

    data = PanelData(
        level=1,
        total=2,
        used=1,
        collected="",
        jobs=[PanelJob(name="臭鸡蛋", count=1, remaining="5 小时 12 分钟")],
    )
    markdown = await build_panel_markdown("panel-user", data, clickable=True)

    assert markdown.startswith("## 🛠 合成机 · Lv.1")
    assert "> 槽位 **1/2** · 升级至 Lv.2（4 槽位）需 **300 VimCoin**" in markdown
    assert "### 进行中的合成" in markdown
    assert "- **臭鸡蛋 x1** · 剩余 5 小时 12 分钟" in markdown
    assert "### 配方" in markdown
    assert "**臭鸡蛋 x1** · 耗时 6 小时 0 分钟" in markdown
    assert "> 材料：鸡蛋x1 · 费用：**10 VimCoin**" in markdown
    assert '<qqbot-cmd-input text="/craft start rotten_egg 1" show="开始合成臭鸡蛋" reference="false" />' in markdown
    # 文本指令提示已从 QQ 面板移除，只保留 cmd-input 与下方键盘按钮
    assert "/craft collect" not in markdown
    assert "/craft upgrade" not in markdown
    assert "收取成品与升级合成机请使用下方按钮" in markdown


@pytest.mark.asyncio
async def test_panel_markdown_plain_for_other_adapters(panel_texts: None) -> None:
    """其它适配器没有 cmd-input 渲染能力，配方改用完整指令，避免未知标签变成空白"""
    from nonebot_plugin_craft.panel import PanelData, build_panel_markdown

    markdown = await build_panel_markdown(
        "panel-user",
        PanelData(level=2, total=4, used=0, collected="", jobs=[]),
        clickable=False,
    )

    assert "qqbot-cmd-input" not in markdown
    assert "> 指令：/craft start rotten_egg 1" in markdown
    assert "> 暂无进行中的合成，还有 4 个空槽位" in markdown


@pytest.mark.asyncio
async def test_panel_buttons_target_craft_commands(panel_texts: None) -> None:
    from nonebot_plugin_craft.panel import build_panel_buttons

    buttons = await build_panel_buttons("panel-user")

    assert [button.flag for button in buttons] == ["enter", "enter", "enter"]
    assert [button.text for button in buttons] == ["/craft collect", "/craft upgrade", "/craft"]


@pytest.mark.asyncio
async def test_start_buttons_open_machine_panel(panel_texts: None) -> None:
    """「已开始合成」提示下方只放一个回到合成机面板的按钮"""
    from nonebot_plugin_craft.panel import build_start_buttons

    buttons = await build_start_buttons("panel-user")

    assert [button.flag for button in buttons] == ["enter"]
    assert [button.label for button in buttons] == ["查看合成机"]
    assert [button.text for button in buttons] == ["/craft"]


@pytest.mark.asyncio
async def test_panel_text_fallback_keeps_previous_layout(panel_texts: None) -> None:
    from nonebot_plugin_craft.panel import PanelData, PanelJob, build_panel_text

    data = PanelData(
        level=1,
        total=2,
        used=0,
        collected="已完成合成：鸡蛋x1（产物已放入背包）",
        jobs=[PanelJob(name="臭鸡蛋", count=1, remaining="1 小时 0 分钟")],
    )
    text = await build_panel_text("panel-user", data)

    assert text.startswith("【合成机】等级 1（可同时合成 2 个物品）")
    assert "槽位占用：0 / 2" in text
    assert "已完成合成：鸡蛋x1（产物已放入背包）" in text
    assert "· 臭鸡蛋 —— 剩余 1 小时 0 分钟" in text
    assert "recipe" not in text  # 配方行里展示配方 ID，不应把键名拼进去


@pytest.mark.asyncio
async def test_send_panel_renders_markdown_image_on_other_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_craft import __main__ as craft_main
    from nonebot_plugin_craft.panel import PanelData

    rendered: dict[str, str] = {}

    async def fake_md_to_pic(markdown: str) -> bytes:
        rendered["markdown"] = markdown
        return b"fake-image"

    finished = AsyncMock()
    monkeypatch.setattr(craft_main, "md_to_pic", fake_md_to_pic)
    monkeypatch.setattr(craft_main.craft, "finish", finished)

    await craft_main.send_panel(MagicMock(), MagicMock(), "panel-user", PanelData(1, 2, 0, "", []))

    assert "合成机" in rendered["markdown"]
    assert "qqbot-cmd-input" not in rendered["markdown"]
    message = finished.await_args.args[0]
    assert any(segment.type == "image" for segment in message)


@pytest.mark.asyncio
async def test_send_panel_falls_back_to_text_when_rendering_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_craft import __main__ as craft_main
    from nonebot_plugin_craft.panel import PanelData

    async def broken_md_to_pic(_markdown: str) -> bytes:
        raise RuntimeError("browser not available")

    finished = AsyncMock()
    monkeypatch.setattr(craft_main, "md_to_pic", broken_md_to_pic)
    monkeypatch.setattr(craft_main.craft, "finish", finished)

    await craft_main.send_panel(MagicMock(), MagicMock(), "panel-user", PanelData(1, 2, 0, "", []))

    sent = finished.await_args.args[0]
    assert isinstance(sent, str)
    assert "合成机" in sent


@pytest.mark.asyncio
async def test_send_started_adds_view_machine_button_for_qq(panel_texts: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人：开始合成提示改用 markdown 消息，并附上「查看合成机」按钮"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot.exception import FinishedException
    from nonebot_plugin_alconna.uniseg import Keyboard, Text, UniMessage

    from nonebot_plugin_craft import __main__ as craft_main

    sent: list[UniMessage] = []

    async def fake_send(self: UniMessage, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    async def fake_finish(*_args: object, **_kwargs: object) -> None:
        raise FinishedException

    monkeypatch.setattr(UniMessage, "send", fake_send)
    monkeypatch.setattr(craft_main.craft, "finish", fake_finish)

    with pytest.raises(FinishedException):
        await craft_main.send_started(MagicMock(spec=QQBot), MagicMock(), "started-user", "臭鸡蛋", 4, "5 小时 59 分钟")

    assert len(sent) == 1
    text = next(segment for segment in sent[0] if isinstance(segment, Text))
    assert any("markdown" in styles for styles in text.styles.values())
    assert text.text == "已开始合成 臭鸡蛋 x4，预计 5 小时 59 分钟 后完成，完成后会被定时发放到背包。"
    keyboard = next(segment for segment in sent[0] if isinstance(segment, Keyboard))
    assert [(button.label, button.text) for button in keyboard.children] == [("查看合成机", "/craft")]


@pytest.mark.asyncio
async def test_send_started_keeps_plain_text_for_other_adapters(
    panel_texts: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """其它适配器没有键盘按钮，开始合成提示保持纯文本"""
    from nonebot_plugin_alconna.uniseg import UniMessage

    from nonebot_plugin_craft import __main__ as craft_main

    send = AsyncMock()
    finished = AsyncMock()
    finished_text = AsyncMock()
    monkeypatch.setattr(UniMessage, "send", send)
    monkeypatch.setattr(craft_main.craft, "finish", finished)
    monkeypatch.setattr(craft_main.lang, "finish", finished_text)

    await craft_main.send_started(MagicMock(), MagicMock(), "started-user", "臭鸡蛋", 4, "5 小时 59 分钟")

    send.assert_not_awaited()
    finished.assert_not_awaited()
    assert finished_text.await_args.args == (
        "start.started",
        "started-user",
        "臭鸡蛋",
        4,
        "5 小时 59 分钟",
    )
