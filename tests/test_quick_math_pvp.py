"""quick math PvP 子命令路由与房间卡片的回归测试。

覆盖的修复点：

- ``/qm pvp create``、``/qm pvp join`` 等子命令曾被 ``/qm pvp`` 帮助处理器抢先
  结束事件，导致子命令永远不生效；现在帮助处理器只在没有匹配到任何 ``pvp``
  子命令时执行；
- PvP 帮助卡片改用 markdown 发送（QQ 官方机器人附带四个操作按钮），
  OneBot 11 等无键盘与 markdown 的适配器退化为把 markdown 渲染成图片；
- QQ 官方机器人下创建房间也会展示房间信息（房间码、总人数、玩家列表）与操作按钮。

注意：插件导入必须在 fixture/函数内部进行（collection 阶段 nonebot 插件尚未加载）。
"""

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
    """QQ 帮助卡片应为 markdown（而非纯文本），并附带四个操作按钮。"""
    from nonebot_plugin_alconna import Keyboard, Text
    from nonebot_plugin_quick_math.commands.pvp import build_pvp_help_message

    message = await build_pvp_help_message("user")
    text = next(segment for segment in message if isinstance(segment, Text))
    assert text.text == _load_template("pvp.help").format(__prefix__="/").strip()
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
    """OneBot 11 等适配器没有键盘与 markdown，帮助页面应渲染成图片发送。"""
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

    assert captured["markdown"] == _load_template("pvp.help").format(__prefix__="/").strip()
    image = next(segment for segment in finished["message"] if isinstance(segment, Image))
    assert image.raw == b"pvp-help-image"


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
