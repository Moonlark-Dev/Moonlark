"""quick math 在 QQ 官方机器人适配器下行为修复的回归测试。

覆盖的修复点：

- 主界面模式按钮分行（keyboard 每行一个按钮），私聊（C2C）下禅模式按钮改为
  input 类型，点击后预填指令供用户自行填入等级，而不是直接发送固定等级 5 的
  ``/qm zen 5``；
- 题目卡片“请选择答案”标题与题目之间补空行，避免标题与题目粘在同一行导致
  QQ markdown 无法解析、原样显示 ``##``；
- 退出指令（leave/quit/q）仅在禅模式（``enable_leave_command``）下生效，且
  q 不再被 prompt 的快捷退出吞掉、超时以 ``ReplyType.TIMEOUT`` 返回，保证
  退出/超时后正常发送结算卡片；
- 结算卡片弃用 QQ 不支持的 markdown 表格，改为 ``> -`` 无序列表；
- 积分命令误用其他插件的 LangHelper 且文案键缺失，导致点击“积分”无响应；
- 排行命令手写 markdown 引用了不存在的键（yaml 键名为连字符、代码用下划线），
  改为使用 nonebot_plugin_ranking 渲染排行。
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
    """用本地化文件中的真实模板替换 LangHelper.text，避免依赖数据库。

    注意：插件导入必须在 fixture/函数内部进行（collection 阶段 nonebot 插件尚未加载）。
    """
    from nonebot_plugin_larkutils.command import config as command_config
    from nonebot_plugin_quick_math.__main__ import lang

    monkeypatch.setattr(command_config, "command_start", ["/"])

    async def fake_text(key: str, _user_id: str, *args: object, **kwargs: object) -> str:
        from nonebot_plugin_larklang.__main__ import builtin_format, remove_trailing_blank_lines

        text = _load_template(key)
        return remove_trailing_blank_lines(text.format(*args, **kwargs, **builtin_format))

    monkeypatch.setattr(lang, "text", fake_text)


def _make_question() -> dict[str, Any]:
    """构造一个答案恒为错误的题目，避免依赖真实题目生成器。"""

    async def answer_fn(_: str) -> bool:
        return False

    return {
        "question": {"question": "1 + 1 = ?", "answer": answer_fn},
        "max_point": 10,
        "level": 1,
        "limit_in_sec": 5,
    }


def _make_choice_question() -> dict[str, Any]:
    """构造一个带选项的选择题。"""

    async def answer_fn(_: str) -> bool:
        return True

    return {
        "question": {
            "question": "1 + 2 = ?",
            "answer": answer_fn,
            "options": ["1", "2", "3"],
        },
        "max_point": 10,
        "level": 1,
        "limit_in_sec": 5,
    }


# ---------- 主界面按钮 ----------


@pytest.mark.asyncio
async def test_menu_c2c_zen_button_prefills_input() -> None:
    """C2C 私聊下禅模式按钮应为 input 类型，预填 ``/qm zen `` 供用户填入等级。"""
    from nonebot_plugin_quick_math.commands.menu import get_menu_buttons

    buttons = await get_menu_buttons("user", private=True)
    assert len(buttons) == 5
    zen = buttons[1]
    assert zen.flag == "input"
    assert zen.text == "/qm zen "
    assert all(button.flag == "enter" for index, button in enumerate(buttons) if index != 1)


@pytest.mark.asyncio
async def test_menu_group_zen_button_sends_default_level() -> None:
    """群聊下禅模式按钮保持 enter 类型，直接发送固定等级 5 的指令。"""
    from nonebot_plugin_quick_math.commands.menu import get_menu_buttons

    buttons = await get_menu_buttons("user", private=False)
    zen = buttons[1]
    assert zen.flag == "enter"
    assert zen.text == "/qm zen 5"
    assert all(button.flag == "enter" for button in buttons)


# ---------- 题目卡片 ----------


@pytest.mark.asyncio
async def test_question_card_choices_heading_on_separate_line() -> None:
    """“请选择答案”标题与题目之间应有空行，不能粘在同一行导致 ## 原样显示。"""
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    question = _make_choice_question()
    message, _ = await build_markdown_message("user", question, 0, 0, 0, 0, "qq_openid")
    assert isinstance(message, UniMessage)
    text = next(segment for segment in message if isinstance(segment, Text))
    content = text.text
    assert "## 请选择答案" in content
    assert "\n\n## 请选择答案" in content
    assert "?## 请选择答案" not in content


@pytest.mark.asyncio
async def test_question_card_leave_button_only_when_enabled() -> None:
    """禅模式（enable_leave_button）下题目卡片应附“退出挑战”（leave）按钮。"""
    from nonebot_plugin_alconna import Keyboard, UniMessage
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    question = _make_choice_question()
    message, _ = await build_markdown_message("user", question, 0, 0, 0, 0, enable_leave_button=True)
    assert isinstance(message, UniMessage)
    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert any(button.text == "leave" for button in keyboard.children)

    message, _ = await build_markdown_message("user", question, 0, 0, 0, 0, enable_leave_button=False)
    assert isinstance(message, UniMessage)
    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert all(button.text != "leave" for button in keyboard.children)


# ---------- 等待回答 / 退出 / 超时 ----------


@pytest.mark.asyncio
async def test_wait_answer_leave_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """“leave”仅在禅模式（enable_leave_command）下作为退出指令生效。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.types import ExtendReplyType, ReplyType
    from nonebot_plugin_quick_math.utils import message as message_module

    async def prompt_stub(_message: UniMessage, _user_id: str, **_kwargs: object) -> str:
        return "leave"

    monkeypatch.setattr(message_module, "prompt", prompt_stub)

    result = await message_module.wait_answer(_make_question(), UniMessage(), "user", enable_leave_command=False)
    assert result is ReplyType.WRONG
    result = await message_module.wait_answer(_make_question(), UniMessage(), "user", enable_leave_command=True)
    assert result is ExtendReplyType.LEAVE


@pytest.mark.asyncio
async def test_wait_answer_q_exits_zen(monkeypatch: pytest.MonkeyPatch) -> None:
    """禅模式下输入 q 应作为退出指令结算，而不是被 prompt 快捷退出吞掉。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.types import ExtendReplyType, ReplyType
    from nonebot_plugin_quick_math.utils import message as message_module

    async def prompt_stub(_message: UniMessage, _user_id: str, **_kwargs: object) -> str:
        return "q"

    monkeypatch.setattr(message_module, "prompt", prompt_stub)

    result = await message_module.wait_answer(_make_question(), UniMessage(), "user", enable_leave_command=True)
    assert result is ExtendReplyType.LEAVE
    result = await message_module.wait_answer(_make_question(), UniMessage(), "user", enable_leave_command=False)
    assert result is ReplyType.WRONG


@pytest.mark.asyncio
async def test_wait_answer_disables_prompt_quit_for_zen(monkeypatch: pytest.MonkeyPatch) -> None:
    """禅模式下应禁用 prompt 的 q 快捷退出，并关闭错误细节抑制使超时抛出 PromptTimeout。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.utils import message as message_module

    captured: dict[str, object] = {}

    async def prompt_stub(_message: UniMessage, _user_id: str, **_kwargs: object) -> str:
        captured.update(_kwargs)
        return "q"

    monkeypatch.setattr(message_module, "prompt", prompt_stub)

    await message_module.wait_answer(_make_question(), UniMessage(), "user", enable_leave_command=True)
    assert captured["allow_quit"] is False
    assert captured["ignore_error_details"] is False


@pytest.mark.asyncio
async def test_wait_answer_timeout_returns_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """超时应返回 ReplyType.TIMEOUT，由会话结算并发送结算卡片，而非中断会话。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_larkuser.exceptions import PromptTimeout
    from nonebot_plugin_quick_math.types import ReplyType
    from nonebot_plugin_quick_math.utils import message as message_module

    async def prompt_stub(_message: UniMessage, _user_id: str, **_kwargs: object) -> None:
        raise PromptTimeout

    monkeypatch.setattr(message_module, "prompt", prompt_stub)

    assert await message_module.wait_answer(_make_question(), UniMessage(), "user") is ReplyType.TIMEOUT


# ---------- 结算文案 ----------


def test_checkout_template_uses_list_not_table() -> None:
    """结算卡片不应使用 QQ 不支持的 markdown 表格，改为 “> -” 无序列表且占位符数量不变。"""
    checkout = _load_template("main.checkout")
    assert "> - " in checkout
    assert "|" not in checkout
    assert checkout.count("{}") == 12


# ---------- 积分详情 ----------


def test_points_lang_keys_exist() -> None:
    """积分详情文案键必须存在于 quick_math 本地化文件中（曾因缺失导致点击积分无响应）。"""
    no_points = _load_template("points.no_points")
    assert no_points
    info = _load_template("points.info")
    assert info.count("{}") == 2


def test_points_command_uses_own_lang() -> None:
    """积分命令应使用 quick_math 自身的 LangHelper，而非其他插件的（曾误用导致查找不到文案）。"""
    from nonebot_plugin_quick_math.__main__ import lang as quick_math_lang
    from nonebot_plugin_quick_math.commands import points

    assert points.lang is quick_math_lang


# ---------- 排行 ----------


def test_rank_command_uses_ranking_plugin() -> None:
    """排名命令应使用 nonebot_plugin_ranking 的 generate_image 渲染，而非手写 markdown。"""
    from nonebot_plugin_quick_math.commands import rank

    assert rank.generate_image.__module__ == "nonebot_plugin_ranking.generator"
    # 排行渲染不应再引用曾导致键缺失的手写 markdown 键
    assert not hasattr(rank, "generate_rank_markdown")


def test_rank_lang_section_no_stale_keys() -> None:
    """rank 文案段不应再包含名称不一致的条目键（md-item/md_info 混用曾导致键缺失）。"""
    data = yaml.safe_load(_LANG_FILE.read_text(encoding="utf-8"))
    rank_section = data["rank"]
    assert "title-1" in rank_section
    assert "title-2" in rank_section
    assert "default_nickname" in rank_section
    for stale in ("md-item", "md-info", "md-me", "md_item", "md_info", "md_me"):
        assert stale not in rank_section


# ---------- L7 题目 ----------


@pytest.mark.asyncio
async def test_l7_generates_no_limit_questions() -> None:
    """L7 求极限题目已暂时停用（过于简单），只应生成一阶/二阶求导题。"""
    from nonebot_plugin_quick_math.utils.generator.levels import l7

    for _ in range(30):
        question = await l7.generate_question("user")
        assert "极限" not in question["question"]
        assert "求导" in question["question"] or "导数" in question["question"]
