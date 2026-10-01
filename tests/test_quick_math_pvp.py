"""quick math PvP 子命令路由与房间卡片的回归测试。

覆盖的修复点：

- ``/qm pvp create``、``/qm pvp join`` 等子命令曾被 ``/qm pvp`` 帮助处理器抢先
  结束事件，导致子命令永远不生效；现在帮助处理器只在没有匹配到任何 ``pvp``
  子命令时执行；
- PvP 帮助卡片改用 markdown 发送（QQ 官方机器人附带四个操作按钮），
  OneBot 11 等无键盘与 markdown 的适配器退化为把 markdown 渲染成图片；
- 帮助处理器曾对 ``build_pvp_help_message`` 返回的协程对象直接调用 ``send()``，
  在 QQ 官方机器人下抛出 ``TypeError: coroutine.send() takes no keyword arguments``；
  现在先 ``await`` 得到 ``UniMessage`` 再发送；
- QQ 官方机器人下的帮助卡片只保留标题与玩法介绍（操作已经在按钮里），
  OneBot 11 等无按钮适配器渲染的图片仍保留完整指令列表；
- QQ 官方机器人下创建房间也会展示房间信息（房间码、总人数、玩家列表）与操作按钮。

- 结算表格的排名按淘汰顺序计算（坚持到最后的人第一），而不是按积分降序：
  积分更高的玩家可能更早被淘汰，旧实现会让亚军排在冠军前面；
- 结算表格里获胜者的积分曾恒为 0：``final_point`` 只在 ``eliminate`` 里赋值，
  而获胜者从未被淘汰；现在得分直接取自玩家会话。

注意：插件导入必须在 fixture/函数内部进行（collection 阶段 nonebot 插件尚未加载）。
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

_LANG_FILE = Path(__file__).resolve().parents[1] / "src" / "lang" / "zh_hans" / "quick_math.yaml"


def _load_template(key: str) -> str:
    """读取本地化文件中的模板，避免依赖数据库读取语言文本。"""
    data = yaml.safe_load(_LANG_FILE.read_text(encoding="utf-8"))
    value: Any = data
    for part in key.split("."):
        value = value[part]
    return value


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """用本地化文件中的真实模板替换 LangHelper.text，避免依赖数据库。"""
    from nonebot_plugin_larkutils.command import config as command_config
    from nonebot_plugin_quick_math.__main__ import lang

    monkeypatch.setattr(command_config, "command_start", ["/"])

    async def fake_text(key: str, _user_id: str, *args: object, **kwargs: object) -> str:
        from nonebot_plugin_larklang.__main__ import builtin_format, remove_trailing_blank_lines

        return remove_trailing_blank_lines(_load_template(key).format(*args, **kwargs, **builtin_format))

    monkeypatch.setattr(lang, "text", fake_text)


def _help_markdown(append_commands: bool) -> str:
    """PvP 帮助 markdown：QQ 适配器只有标题与介绍，无按钮的适配器追加指令列表。

    与 ``get_pvp_help_markdown`` 一致：每段文本先去掉 YAML 块标量结尾的空行，
    再用空行拼接，最后填充指令前缀。
    """
    parts = [_load_template("pvp.help").strip()]
    if append_commands:
        parts.append(_load_template("pvp.help_commands").strip())
    return "\n\n".join(parts).format(__prefix__="/")


def _parse(text: str) -> Any:
    """用插件真实的 Alconna 命令解析输入，得到 Arparma。

    启用 ``ALCONNA_USE_COMMAND_START`` 后 Alconna 会要求命令前缀，
    因此按 nonebot 全局配置补上前缀（实际消息由适配器剥离前缀后传入命令）。
    """
    from nonebot import get_driver
    from nonebot_plugin_quick_math.__main__ import quick_math

    prefix = next(iter(get_driver().config.command_start or ["/"]))
    result = quick_math.command().parse(f"{prefix}{text}")
    assert getattr(result, "matched", False), f"命令解析失败：{text} -> {result!r}"
    return result


# ---------- 子命令路由 ----------


@pytest.mark.parametrize(
    "text",
    [
        "qm pvp create",
        "qm pvp create 3",
        "qm pvp join ABCDE",
        "qm pvp quit",
        "qm pvp start",
    ],
)
@pytest.mark.asyncio
async def test_pvp_help_check_rejects_subcommands(text: str) -> None:
    """带子命令的输入不应命中 pvp 帮助处理器，否则子命令永远不会执行。"""
    from nonebot_plugin_quick_math.commands.pvp import is_pvp_help_only

    result = _parse(text)
    assert await is_pvp_help_only(None, None, {}, result) is False


@pytest.mark.asyncio
async def test_pvp_help_check_accepts_bare_pvp() -> None:
    """只有输入 ``pvp`` 本身时才展示帮助。"""
    from nonebot_plugin_quick_math.commands.pvp import is_pvp_help_only

    result = _parse("qm pvp")
    assert await is_pvp_help_only(None, None, {}, result) is True


# ---------- 帮助卡片 ----------


@pytest.mark.asyncio
async def test_pvp_help_message_is_markdown_with_buttons() -> None:
    """QQ 帮助卡片应为 markdown（而非纯文本），并附带四个操作按钮。

    QQ 卡片下方已经提供了全部操作的按钮，正文只保留标题与玩法介绍，
    不再重复展示一份指令列表。
    """
    from nonebot_plugin_alconna import Keyboard, Text
    from nonebot_plugin_quick_math.commands.pvp import build_pvp_help_message

    message = await build_pvp_help_message("user")
    text = next(segment for segment in message if isinstance(segment, Text))
    assert text.text == _help_markdown(append_commands=False)
    assert _load_template("pvp.help_commands").format(__prefix__="/").strip() not in text.text
    assert "markdown" in text.styles[next(iter(text.styles))]
    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert [button.flag for button in keyboard.children] == ["enter", "input", "enter", "enter"]
    assert [button.text for button in keyboard.children] == [
        "/qm pvp create",
        "/qm pvp join ",
        "/qm pvp quit",
        "/qm pvp start",
    ]


@pytest.mark.asyncio
async def test_pvp_help_renders_image_on_onebot(monkeypatch: pytest.MonkeyPatch) -> None:
    """OneBot 11 等适配器没有键盘与 markdown，帮助页面应渲染成图片发送。

    这类适配器没有可点击的按钮，图片内需要保留完整的指令列表。
    """
    from nonebot.adapters.console import Bot as ConsoleBot
    from nonebot_plugin_alconna import Image, UniMessage
    from nonebot_plugin_quick_math.commands import pvp as pvp_module

    captured: dict[str, str] = {}

    async def fake_md_to_pic(markdown: str, **_kwargs: object) -> bytes:
        captured["markdown"] = markdown
        return b"pvp-help-image"

    finished: dict[str, UniMessage] = {}

    async def fake_finish(message: UniMessage | None = None, **_kwargs: object) -> None:
        assert message is not None
        finished["message"] = message

    monkeypatch.setattr(pvp_module, "md_to_pic", fake_md_to_pic)
    monkeypatch.setattr(pvp_module.quick_math, "finish", fake_finish)

    await pvp_module.pvp_help_handler(ConsoleBot.__new__(ConsoleBot), None, user_id="user")

    assert captured["markdown"] == _help_markdown(append_commands=True)
    image = next(segment for segment in finished["message"] if isinstance(segment, Image))
    assert image.raw == b"pvp-help-image"


@pytest.mark.asyncio
async def test_pvp_help_sends_keyboard_card_on_qq(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人下帮助处理器必须先 await 构建协程，再发送 markdown 卡片。

    回归点：``build_pvp_help_message`` 是协程函数，遗漏 ``await`` 会对协程对象调用
    ``send()``，抛出 ``TypeError: coroutine.send() takes no keyword arguments``。
    """
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna import Keyboard, UniMessage
    from nonebot_plugin_quick_math.commands import pvp as pvp_module

    class _FinishedError(Exception):
        """占位异常：模拟 quick_math.finish 结束事件处理器。"""

    captured: dict[str, Any] = {}

    async def fake_send(
        self: UniMessage,
        target: Any = None,
        bot: Any = None,
        **_kwargs: object,
    ) -> None:
        captured["message"] = self
        captured["target"] = target
        captured["bot"] = bot

    async def fake_finish(message: UniMessage | None = None, **_kwargs: object) -> None:
        captured["finished"] = message
        raise _FinishedError

    monkeypatch.setattr(UniMessage, "send", fake_send)
    monkeypatch.setattr(pvp_module.quick_math, "finish", fake_finish)

    bot = QQBot.__new__(QQBot)
    event = object()
    with pytest.raises(_FinishedError):
        await pvp_module.pvp_help_handler(bot, event, user_id="user")

    message = captured["message"]
    assert isinstance(message, UniMessage)
    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert [button.text for button in keyboard.children] == [
        "/qm pvp create",
        "/qm pvp join ",
        "/qm pvp quit",
        "/qm pvp start",
    ]
    assert captured["target"] is event
    assert captured["bot"] is bot
    # QQ 分支发送卡片后单独 finish，不应再走到渲染图片的分支
    assert captured["finished"] is None


# ---------- 房间卡片 ----------


def _make_room(bot: Any, room_id: str = "ABCDE", max_players: int = 5) -> Any:
    from nonebot_plugin_quick_math.utils.pvp import QuickMathRoom, QuickMathRoomPlayer

    room = QuickMathRoom(room_id, "group", "u1", max_players, bot, None)
    room.players.append(QuickMathRoomPlayer("u1", "qq1", None))
    return room


@pytest.fixture(autouse=True)
def patched_nickname(monkeypatch: pytest.MonkeyPatch) -> None:
    """固定玩家昵称，避免查询数据库。"""
    from nonebot_plugin_quick_math.utils.pvp import QuickMathRoom

    async def fake_get_nickname(_self: Any, user_id: str) -> str:
        return f"昵称-{user_id}"

    monkeypatch.setattr(QuickMathRoom, "get_nickname", fake_get_nickname)


@pytest.mark.asyncio
async def test_qq_create_message_shows_room_info_and_buttons() -> None:
    """QQ 下创建房间应展示房间码、总人数与玩家列表，并附带操作按钮。"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna import Keyboard, Text

    room = _make_room(QQBot.__new__(QQBot))
    message = await room.build_create_message("u1")
    content = next(segment for segment in message if isinstance(segment, Text)).text
    assert "房间已创建（5 人房）" in content
    assert "ABCDE" in content
    assert "玩家（1/5）" in content
    assert "1. 昵称-u1 （房主）" in content

    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert [button.text for button in keyboard.children] == ["/qm pvp start", "/qm pvp join ABCDE", "/qm pvp quit"]


@pytest.mark.asyncio
async def test_qq_join_message_hides_join_button_when_full() -> None:
    """房间满员后不再展示加入按钮，但保留开始与退出按钮。"""
    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna import Keyboard
    from nonebot_plugin_quick_math.utils.pvp import QuickMathRoomPlayer

    room = _make_room(QQBot.__new__(QQBot), max_players=2)
    room.players.append(QuickMathRoomPlayer("u2", "qq2", None))
    message = await room.build_player_list_message("u1")
    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert [button.text for button in keyboard.children] == ["/qm pvp start", "/qm pvp quit"]


@pytest.mark.asyncio
async def test_onebot_room_message_stays_plain_text() -> None:
    """OneBot 11 等适配器没有键盘：房间信息保持纯文本并附上加入指令。"""
    from nonebot.adapters.console import Bot as ConsoleBot
    from nonebot_plugin_alconna import Keyboard, Text

    room = _make_room(ConsoleBot.__new__(ConsoleBot))
    message = await room.build_player_list_message("u1")
    content = next(segment for segment in message if isinstance(segment, Text)).text
    assert "ABCDE" in content
    assert "玩家（1/5）" in content
    assert "/qm pvp join ABCDE" in content
    assert not any(isinstance(segment, Keyboard) for segment in message)


# ---------- 结算排名与积分 ----------


class _FakePvpSession:
    """结算只需要会话里的统计数据，用假会话避免真正出题与写库。"""

    def __init__(self, point: int, passed: int, total_answered: int, skipped: int = 0) -> None:
        self.point = point
        self.passed = passed
        self.total_answered = total_answered
        self.skipped_question = skipped
        self.achievement_updated = False

    async def update_achievement(self) -> None:
        self.achievement_updated = True


def _result_rows(markdown: str) -> list[list[str]]:
    """取出结算表格的数据行（跳过表头与对齐行），每个单元格去掉空白。"""
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in markdown.splitlines()
        if re.match(r"^\|\s*\d+\s*\|", line)
    ]


@pytest.mark.asyncio
async def test_eliminate_records_elimination_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """淘汰时记录淘汰顺序，并用会话里的真实积分（而非另存一份可能漏写的字段）。"""
    from nonebot.adapters.console import Bot as ConsoleBot
    from nonebot_plugin_quick_math.utils import pvp as pvp_module
    from nonebot_plugin_quick_math.utils.pvp import QuickMathRoom, QuickMathRoomPlayer

    async def fake_update_user_data(_user_id: str, _point: int) -> tuple[int, int]:
        return 0, 0

    broadcasts: list[tuple[str, tuple[object, ...]]] = []

    async def fake_broadcast_lang(_self: Any, key: str, _user_id: str, *args: object) -> None:
        broadcasts.append((key, args))

    monkeypatch.setattr(pvp_module, "update_user_data", fake_update_user_data)
    monkeypatch.setattr(QuickMathRoom, "broadcast_lang", fake_broadcast_lang)

    room = QuickMathRoom("ABCDE", "group", "u1", 2, ConsoleBot.__new__(ConsoleBot), None)
    player = QuickMathRoomPlayer("u2", None, None)
    session = _FakePvpSession(point=19, passed=8, total_answered=9)
    player.session = session  # type: ignore[assignment]

    await room.eliminate(player)

    assert room.eliminated == [player]
    assert player.saved is True
    assert player.final_point == 19
    assert session.achievement_updated is True
    assert broadcasts[-1] == ("pvp.eliminated", ("昵称-u2", 19))

    # 已淘汰的玩家不会重复记录（quit 与答错可能先后触发淘汰）
    await room.eliminate(player)
    assert room.eliminated == [player]


@pytest.mark.asyncio
async def test_result_markdown_ranks_by_elimination_order() -> None:
    """结算排名按淘汰顺序：先被淘汰的排后面，获胜者第一且显示真实积分。

    回归点：旧实现按积分降序排序，而获胜者从未被淘汰、积分为 0，
    于是获胜者被排到已被淘汰的玩家后面，表格里积分为 0。
    """
    from nonebot.adapters.console import Bot as ConsoleBot
    from nonebot_plugin_quick_math.utils.pvp import QuickMathRoom, QuickMathRoomPlayer

    room = QuickMathRoom("ABCDE", "group", "u1", 3, ConsoleBot.__new__(ConsoleBot), None)
    winner = QuickMathRoomPlayer("u1", None, None)
    runner_up = QuickMathRoomPlayer("u2", None, None)
    first_out = QuickMathRoomPlayer("u3", None, None)
    winner.session = _FakePvpSession(point=23, passed=8, total_answered=8)  # type: ignore[assignment]
    runner_up.session = _FakePvpSession(point=19, passed=8, total_answered=9, skipped=1)  # type: ignore[assignment]
    first_out.session = _FakePvpSession(point=5, passed=2, total_answered=3)  # type: ignore[assignment]
    room.order = [winner, runner_up, first_out]
    room.players = [winner]
    # 先淘汰 first_out，再淘汰 runner_up，最后剩下 winner
    room.eliminated = [first_out, runner_up]

    markdown = await room.build_result_markdown()

    assert room.get_ranking() == [winner, runner_up, first_out]
    rows = _result_rows(markdown)
    assert [row[0] for row in rows] == ["1", "2", "3"]
    assert [row[1] for row in rows] == ["昵称-u1", "昵称-u2", "昵称-u3"]
    # 获胜者的积分是其会话真实得分，不再是 0
    assert [row[2] for row in rows] == ["23", "19", "5"]
    assert [row[3] for row in rows] == ["8", "8", "2"]
    assert [row[4] for row in rows] == ["100%", "89%", "67%"]
    assert [row[5] for row in rows] == ["0", "1", "0"]


@pytest.mark.asyncio
async def test_finish_reports_winner_point_and_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    """完整结算流程：获胜者广播与卡片都使用真实积分，且排在第一名。"""
    from nonebot.adapters.console import Bot as ConsoleBot
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.utils import pvp as pvp_module
    from nonebot_plugin_quick_math.utils.pvp import QuickMathRoom, QuickMathRoomPlayer

    async def fake_update_user_data(_user_id: str, _point: int) -> tuple[int, int]:
        return 0, 0

    async def fake_md_to_pic(markdown: str, **_kwargs: object) -> bytes:
        rendered["markdown"] = markdown
        return b"pvp-result-image"

    broadcasts: list[tuple[str, tuple[object, ...]]] = []

    async def fake_broadcast_lang(_self: Any, key: str, _user_id: str, *args: object) -> None:
        broadcasts.append((key, args))

    async def fake_send(self: UniMessage, target: Any = None, bot: Any = None, **_kwargs: object) -> None:
        sent["message"] = self
        sent["target"] = target
        sent["bot"] = bot

    rendered: dict[str, str] = {}
    sent: dict[str, Any] = {}

    monkeypatch.setattr(pvp_module, "update_user_data", fake_update_user_data)
    monkeypatch.setattr(pvp_module, "md_to_pic", fake_md_to_pic)
    monkeypatch.setattr(QuickMathRoom, "broadcast_lang", fake_broadcast_lang)
    monkeypatch.setattr(UniMessage, "send", fake_send)

    room = QuickMathRoom("RANKR", "group", "u1", 2, ConsoleBot.__new__(ConsoleBot), None)
    loser = QuickMathRoomPlayer("u1", None, None)
    winner = QuickMathRoomPlayer("u2", None, None)
    loser.session = _FakePvpSession(point=19, passed=8, total_answered=9)  # type: ignore[assignment]
    winner.session = _FakePvpSession(point=23, passed=8, total_answered=8)  # type: ignore[assignment]
    room.order = [loser, winner]
    room.players = [winner]
    room.eliminated = [loser]
    pvp_module.rooms[room.room_id] = room
    try:
        await room.finish()
    finally:
        pvp_module.rooms.pop(room.room_id, None)

    assert broadcasts[-1] == ("pvp.winner", ("昵称-u2", 23))
    rows = _result_rows(rendered["markdown"])
    assert [(row[0], row[1], row[2]) for row in rows] == [("1", "昵称-u2", "23"), ("2", "昵称-u1", "19")]
    assert room.status == "ended"
    assert "RANKR" not in pvp_module.rooms
    assert sent["target"] is None
    assert any(segment.__class__.__name__ == "Image" for segment in sent["message"])
