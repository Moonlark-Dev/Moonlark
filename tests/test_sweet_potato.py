"""烫手山芋玩法的单元测试。

覆盖：概率档位与奖励表、概率抽取特例、爆炸判定、传递目标解析、
捂热 / 传递的状态变化，以及 QQ 面板、结算面板和本地化键的构建。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml

_LANG_FILE = Path(__file__).resolve().parents[1] / "src" / "lang" / "zh_hans" / "sweet_potato.yaml"


def _load_template(key: str) -> Any:
    value: Any = yaml.safe_load(_LANG_FILE.read_text(encoding="utf-8"))
    for part in key.split("."):
        value = value[part]
    return value


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """用本地化文件中的真实模板替换 LangHelper.text，避免依赖数据库。"""
    from nonebot_plugin_larkutils.command import config as command_config
    from nonebot_plugin_sweet_potato.lang import lang

    monkeypatch.setattr(command_config, "command_start", ["/"])

    async def fake_text(key: str, _user_id: str, *args: object, **kwargs: object) -> str:
        from nonebot_plugin_larklang.__main__ import builtin_format, remove_trailing_blank_lines

        return remove_trailing_blank_lines(_load_template(key).format(*args, **kwargs, **builtin_format))

    monkeypatch.setattr(lang, "text", fake_text)


# ---------- 概率档位与奖励 ----------


def test_risk_level_boundaries() -> None:
    from nonebot_plugin_sweet_potato.logic import get_risk_level

    cases = {
        0: "safe",
        50: "safe",
        51: "low",
        70: "low",
        71: "medium",
        89: "medium",
        90: "high",
        94: "high",
        95: "extreme",
        98: "extreme",
        99: "imminent",
        100: "imminent",
    }
    for probability, level in cases.items():
        assert get_risk_level(probability) == level, probability


def test_reward_table() -> None:
    from nonebot_plugin_sweet_potato.logic import get_reward

    assert get_reward(0, "pass") == 0
    assert get_reward(50, "hold") == 0
    assert get_reward(60, "pass") == 1
    assert get_reward(60, "hold") == 3
    assert get_reward(80, "pass") == 2
    assert get_reward(80, "hold") == 5
    assert get_reward(92, "pass") == 3
    assert get_reward(92, "hold") == 8
    assert get_reward(97, "pass") == 6
    assert get_reward(97, "hold") == 15
    assert get_reward(100, "pass") == 12
    assert get_reward(100, "hold") == 30


# ---------- 概率抽取 ----------


def test_initial_probability_in_range() -> None:
    from nonebot_plugin_sweet_potato.logic import draw_initial_probability

    for _ in range(200):
        assert 30 <= draw_initial_probability() <= 60


def test_draw_probability_updates_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import logic

    calls: list[tuple[int, int]] = []

    def fake_randint(lower: int, upper: int) -> int:
        calls.append((lower, upper))
        return upper

    monkeypatch.setattr(logic.random, "randint", fake_randint)
    assert logic.draw_probability(60) == (100, 100)
    assert calls == [(60, 100)]


def test_draw_probability_short_circuit_after_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import logic

    values: Iterator[int] = iter([95, 57])
    calls: list[tuple[int, int]] = []

    def fake_randint(lower: int, upper: int) -> int:
        calls.append((lower, upper))
        return next(values)

    monkeypatch.setattr(logic.random, "randint", fake_randint)
    monkeypatch.setattr(logic.random, "random", lambda: 0.0)

    probability, floor = logic.draw_probability(60, after_pass=True)
    assert probability == 57
    # 特例不更新下限
    assert floor == 60
    assert calls == [(60, 100), (55, 60)]


def test_draw_probability_no_short_circuit_when_not_triggered(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import logic

    monkeypatch.setattr(logic.random, "randint", lambda _lower, upper: upper)
    monkeypatch.setattr(logic.random, "random", lambda: 0.5)

    probability, floor = logic.draw_probability(60, after_pass=True)
    assert probability == 100
    assert floor == 100


def test_draw_probability_short_circuit_requires_above_90(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import logic

    calls: list[tuple[int, int]] = []

    def fake_randint(lower: int, upper: int) -> int:
        calls.append((lower, upper))
        return 90

    monkeypatch.setattr(logic.random, "randint", fake_randint)
    monkeypatch.setattr(logic.random, "random", lambda: 0.0)

    probability, floor = logic.draw_probability(60, after_pass=True)
    assert probability == 90
    assert floor == 90
    # 只有一次抽取，没有触发回落下限的特例
    assert calls == [(60, 100)]


def test_roll_explosion_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import logic

    monkeypatch.setattr(logic.random, "randint", lambda _lower, _upper: 100)
    assert logic.roll_explosion(100) is True
    assert logic.roll_explosion(99) is False

    monkeypatch.setattr(logic.random, "randint", lambda _lower, _upper: 1)
    assert logic.roll_explosion(0) is False
    assert logic.roll_explosion(1) is True


# ---------- 房间状态 ----------


def _make_room(players: int = 3) -> Any:
    from nonebot_plugin_sweet_potato.potatoes import DEFAULT_POTATO_ID, POTATO_TYPES
    from nonebot_plugin_sweet_potato.room import HotPotatoRoom

    room = HotPotatoRoom("qq_1", "u1", None, None, POTATO_TYPES[DEFAULT_POTATO_ID])  # type: ignore[arg-type]
    for index in range(1, players + 1):
        room.add_player(f"u{index}", f"1000{index}", f"玩家{index}")
    room.holder = room.players[0]
    room.status = "playing"
    room.probability = 60
    room.min_probability = 60
    return room


def test_resolve_target_by_index_and_at() -> None:
    from nonebot_plugin_alconna import At

    room = _make_room()
    holder = room.players[1]
    room.holder = holder
    assert room.get_pass_targets() == [(1, room.players[0]), (3, room.players[2])]
    assert room.resolve_target("1") is room.players[0]
    assert room.resolve_target("2") is None  # 不能传给自己
    assert room.resolve_target("3") is room.players[2]
    assert room.resolve_target(At("user", "10003")) is room.players[2]
    assert room.resolve_target(At("user", "99999")) is None
    assert room.resolve_target("random") in [room.players[0], room.players[2]]
    assert room.resolve_target(None) is None


def test_hold_then_pass_counts_successful_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import room as room_module

    room = _make_room()
    monkeypatch.setattr(room_module, "draw_probability", lambda _minimum, **_kwargs: (80, 80))
    assert room.hold_potato() is True
    assert room.probability == 80
    assert room.min_probability == 80
    assert room.pending_holds["u1"] == 1
    assert room.rewards["u1"] == 3  # 低危档捂热 3vi

    monkeypatch.setattr(room_module, "roll_explosion", lambda _probability: False)
    monkeypatch.setattr(room_module, "draw_probability", lambda _minimum, **_kwargs: (85, 85))
    assert room.pass_potato(room.players[1]) is True
    # 捂热后概率升到中危，传递计 2vi
    assert room.rewards["u1"] == 5
    assert room.successful_holds["u1"] == 1
    assert room.total_holds == 1
    assert room.total_passes == 1
    assert room.holder is room.players[1]


def test_pass_explosion_keeps_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import room as room_module

    room = _make_room()
    holder = room.holder
    monkeypatch.setattr(room_module, "roll_explosion", lambda _probability: True)
    assert room.pass_potato(room.players[1]) is False
    assert room.holder is holder
    assert room.total_passes == 0
    assert room.rewards == {}


def test_hold_explodes_on_100(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import room as room_module

    room = _make_room()
    room.probability = 95
    room.min_probability = 95
    monkeypatch.setattr(room_module, "draw_probability", lambda _minimum, **_kwargs: (100, 100))
    assert room.hold_potato() is False
    assert room.total_holds == 0
    assert room.rewards == {}
    assert room.probability == 95


def test_short_circuit_probability_is_used_for_next_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import room as room_module

    room = _make_room()
    room.min_probability = 60
    room.probability = 60
    monkeypatch.setattr(room_module, "roll_explosion", lambda _probability: False)
    monkeypatch.setattr(room_module, "draw_probability", lambda _minimum, **_kwargs: (55, 60))
    assert room.pass_potato(room.players[1]) is True
    assert room.probability == 55
    # 特例不更新下限
    assert room.min_probability == 60


@pytest.mark.asyncio
async def test_run_game_pass_then_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_sweet_potato import room as room_module
    from nonebot_plugin_sweet_potato.room import PotatoAction

    room = _make_room()
    sent: list[Any] = []
    finished: list[tuple[Any, Any]] = []

    async def fake_send(message: Any, event: Any = None) -> None:
        sent.append(message)

    async def fake_finish(burned: Any, reason: Any) -> None:
        finished.append((burned, reason))
        room.status = "ended"

    actions: list[Any] = [PotatoAction(turn=1, kind="pass", target=room.players[1]), None]

    async def fake_wait() -> Any:
        return actions.pop(0)

    monkeypatch.setattr(room, "send", fake_send)
    monkeypatch.setattr(room, "finish", fake_finish)
    monkeypatch.setattr(room, "wait_action", fake_wait)
    monkeypatch.setattr(room_module, "roll_explosion", lambda _probability: False)
    monkeypatch.setattr(room_module, "draw_probability", lambda _minimum, **_kwargs: (85, 85))

    await room.run_game()

    assert room.holder is room.players[1]
    assert finished == [(room.players[1], "timeout")]
    assert len(sent) == 2


# ---------- 面板与结算 ----------


@pytest.mark.asyncio
async def test_panel_markdown_contains_clickable_targets() -> None:
    room = _make_room()
    room.probability = 96
    markdown = await room.build_panel_markdown("游戏开始！山芋在你手里。")
    assert '<qqbot-at-user id="10001" />' in markdown
    assert "### 下一次传递时爆炸概率" in markdown
    assert "**极危**" in markdown
    assert "> ### 可传递对象" in markdown
    assert '<qqbot-cmd-input text="/sweet-potato pass 2" show="玩家2" reference="false" />' in markdown
    assert '<qqbot-cmd-input text="/sweet-potato pass 3" show="玩家3" reference="false" />' in markdown


@pytest.mark.asyncio
async def test_panel_text_lists_targets() -> None:
    room = _make_room()
    room.holder = room.players[1]
    text = await room.build_panel_text("你捂热了山芋，温度更高了。")
    assert "下一次传递时爆炸概率：低危" in text
    assert "1. 玩家1" in text
    assert "3. 玩家3" in text
    assert "sweet-potato pass" in text


@pytest.mark.asyncio
async def test_result_markdown() -> None:
    room = _make_room()
    room.burned = room.players[0]
    room.burn_reason = "hold"
    room.total_holds = 2
    room.total_passes = 3
    room.holds = {"u1": 1, "u2": 1}
    room.passes = {"u1": 2, "u2": 1}
    room.rewards = {"u1": 5, "u2": 7}
    markdown = await room.build_result_markdown()
    assert "烫手山芋 · 结算" in markdown
    assert "玩家1" in markdown
    assert "-10 HP" in markdown
    assert "捂热 **2** 次" in markdown
    assert "传递 **3** 次" in markdown
    assert "- 玩家1：捂热 1 次，传递 2 次，获得 **5 vi**（被烫死）" in markdown
    assert "- 玩家2：捂热 1 次，传递 1 次，获得 **7 vi**" in markdown


# ---------- 结算与数据库 ----------


@pytest.mark.asyncio
async def test_apply_settlement_and_rank_data() -> None:
    from datetime import datetime

    from nonebot_plugin_larkuser.models import UserData
    from nonebot_plugin_orm import get_session
    from nonebot_plugin_sweet_potato.models import SweetPotatoStat
    from nonebot_plugin_sweet_potato.potatoes import DEFAULT_POTATO_ID, POTATO_TYPES
    from nonebot_plugin_sweet_potato.room import HotPotatoRoom, get_rank_data
    from sqlalchemy import delete

    async with get_session() as session:
        await session.execute(delete(SweetPotatoStat).where(SweetPotatoStat.user_id.in_(["sp_u1", "sp_u2"])))
        await session.execute(delete(UserData).where(UserData.user_id.in_(["sp_u1", "sp_u2"])))
        session.add_all(
            [
                UserData(user_id="sp_u1", nickname="甲", register_time=datetime.now(), health=100, vimcoin=0),
                UserData(user_id="sp_u2", nickname="乙", register_time=datetime.now(), health=100, vimcoin=0),
            ],
        )
        await session.commit()

    room = HotPotatoRoom(
        "qq_sp",
        "sp_u1",
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        POTATO_TYPES[DEFAULT_POTATO_ID],
    )
    room.add_player("sp_u1", "10001", "甲")
    room.add_player("sp_u2", "10002", "乙")
    room.burned = room.players[0]
    room.rewards = {"sp_u1": 5, "sp_u2": 7}
    room.successful_holds = {"sp_u1": 1, "sp_u2": 2}
    room.holds = {"sp_u1": 2, "sp_u2": 3}
    room.passes = {"sp_u1": 4, "sp_u2": 5}
    await room.apply_settlement()

    async with get_session() as session:
        burned = await session.get(UserData, "sp_u1")
        survivor = await session.get(UserData, "sp_u2")
        assert burned is not None and burned.health == 90
        assert burned.vimcoin == 5
        assert survivor is not None and survivor.health == 100
        assert survivor.vimcoin == 7
        stat = await session.get(SweetPotatoStat, "sp_u1")
        assert stat is not None
        assert stat.successful_holds == 1
        assert stat.total_holds == 2
        assert stat.total_passes == 4
        assert stat.burn_count == 1
        assert stat.game_count == 1

    data = await get_rank_data("sp_u1")
    mine = [item for item in data if item["user_id"] == "sp_u1"]
    assert mine and mine[0]["data"] == 1


# ---------- 指令与本地化 ----------


def _parse(text: str) -> Any:
    from nonebot import get_driver
    from nonebot_plugin_sweet_potato.__main__ import sweet_potato

    prefix = next(iter(get_driver().config.command_start or ["/"]))
    result = sweet_potato.command().parse(f"{prefix}{text}")
    assert getattr(result, "matched", False), f"命令解析失败：{text} -> {result!r}"
    return result


@pytest.mark.parametrize(
    ("text", "subcommand", "target"),
    [
        ("sweet-potato info", "info", None),
        ("sweet-potato rank", "rank", None),
        ("sweet-potato create", "create", None),
        ("sweet-potato join", "join", None),
        ("sweet-potato start", "start", None),
        ("sweet-potato restart", "restart", None),
        ("sweet-potato quit", "quit", None),
        ("sweet-potato hold", "hold", None),
        ("sweet-potato pass 2", "pass", "2"),
        ("sweet-potato pass random", "pass", "random"),
    ],
)
def test_command_parsing(text: str, subcommand: str, target: str | None) -> None:
    result = _parse(text)
    matched = result.subcommands[subcommand]
    if target is None:
        assert "target" not in matched.args
    else:
        assert matched.args["target"] == target


def test_lang_keys_expand() -> None:
    from nonebot_plugin_larklang.loader import KeysParser

    data = yaml.safe_load(_LANG_FILE.read_text(encoding="utf-8"))
    keys = KeysParser(data, {}).get_keys()
    for key in (
        "game.panel_markdown",
        "game.panel_target_line",
        "game.panel_text",
        "game.summary_start",
        "result.reward_row",
        "result.reason_timeout",
        "info.rules",
        "rank.info",
        "risk.imminent",
        "error.not_your_turn",
    ):
        assert key in keys, key
    # room / game / result 等分组不应被当作叶子节点
    for key in ("game", "result", "info", "room"):
        assert key not in keys, key


def test_default_potato_initial_range() -> None:
    from nonebot_plugin_sweet_potato.potatoes import POTATO_TYPES

    for potato in POTATO_TYPES.values():
        lower, upper = potato.initial_probability_range
        assert lower <= upper
