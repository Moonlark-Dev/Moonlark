"""quick math 在 QQ 官方机器人适配器下行为修复的回归测试。

覆盖的修复点：

- 主界面模式按钮分行（keyboard 每行一个按钮），私聊（C2C）下禅模式按钮改为
  input 类型，点击后预填指令供用户自行填入等级，而不是直接发送固定等级 5 的
  ``/qm zen 5``；
- 一元二次方程（L5）的题目信息（题干 + “请选择答案” + 选项）改用 md_to_pic 渲染成
  图片后经图床发送，避免 QQ markdown 不解析 LaTeX 导致 ``\frac``/``\sqrt`` 显示成
  ``√(57)2`` 这类纯文本；该等级的选项按钮内容改为选项字母（A/B/C/D），选项原文已随
  题目信息进入图片。其余等级的题目信息与选项按钮保持原有纯文本表现；
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

# 图床返回的 markdown 图片代码（含 QQ 需要的宽高标注）
_FAKE_IMAGE_MARKDOWN = "![text #100px #50px](https://example.com/question.jpg)"


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


@pytest.fixture(autouse=True)
def patched_image_renderer(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """拦截题目信息渲染与图床上传，避免测试依赖浏览器与对象存储。

    返回的字典记录传给 md_to_pic 的 markdown 与上传的图片数据，便于断言题目信息
    （题干 + 选项）确实被渲染为图片、而不是继续以纯文本发送。
    """
    from nonebot_plugin_quick_math.utils import question as question_module

    captured: dict[str, Any] = {"markdown": None, "image": None}

    async def fake_md_to_pic(markdown: str, **_kwargs: object) -> bytes:
        captured["markdown"] = markdown
        return b"fake-image"

    async def fake_create_image_markdown(data: bytes, **_kwargs: object) -> str:
        captured["image"] = data
        return _FAKE_IMAGE_MARKDOWN

    monkeypatch.setattr(question_module, "md_to_pic", fake_md_to_pic)
    monkeypatch.setattr(question_module, "create_image_markdown", fake_create_image_markdown)
    return captured


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


def _make_choice_question(answer_fn: Any = None, level: int = 1) -> dict[str, Any]:
    """构造一个带选项的选择题（默认判定恒为正确）。

    ``level`` 决定题目信息是否渲染为图片：只有 L5（一元二次方程）走图片。
    """

    if answer_fn is None:

        async def always_right(_: str) -> bool:
            return True

        answer_fn = always_right

    return {
        "question": {
            "question": "1 + 2 = ?",
            "answer": answer_fn,
            "options": ["1", "2", "3"],
        },
        "max_point": 10,
        "level": level,
        "limit_in_sec": 5,
    }


def _make_recorded_verify(correct: str = "3") -> tuple[dict[str, Any], list[str]]:
    """构造“慢速判定”题目：记录判定函数收到的每次输入，便于断言是否绕过慢速路径。"""
    calls: list[str] = []

    async def answer_fn(string: str) -> bool:
        calls.append(string)
        return string == correct

    return _make_choice_question(answer_fn), calls


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
async def test_question_card_question_info_is_image(patched_image_renderer: dict[str, Any]) -> None:
    """L5（一元二次方程）的“题目信息”标题后应是一张图片，题干与选项都不再以纯文本出现。"""
    from nonebot_plugin_alconna import Text, UniMessage
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    question = _make_choice_question(level=5)
    message, _ = await build_markdown_message("user", question, 0, 0, 0, 0, "qq_openid")
    assert isinstance(message, UniMessage)
    content = next(segment for segment in message if isinstance(segment, Text)).text
    # 图片紧跟在“题目信息”标题之后
    assert f"## 题目信息\n\n{_FAKE_IMAGE_MARKDOWN}" in content
    # 题干与选项都不再直接出现在 QQ markdown 里（否则仍会显示成难读的纯文本）
    assert "1 + 2 = ?" not in content
    assert "A. 1" not in content
    # 图片内容包含题干 LaTeX 原文与“请选择答案”+ 选项列表
    markdown: str = patched_image_renderer["markdown"]
    assert markdown.startswith("1 + 2 = ?")
    assert "\n\n## 请选择答案\n\n" in markdown
    # 选项之间使用行尾双空格的硬换行，否则图片里所有选项会被折叠到同一行
    assert "A. 1  \nB. 2  \nC. 3" in markdown
    assert patched_image_renderer["image"] == b"fake-image"


@pytest.mark.asyncio
async def test_question_card_other_levels_stay_plain_text(patched_image_renderer: dict[str, Any]) -> None:
    """只有 L5 走图片：其余等级仍以纯文本发送题目信息，不触发渲染与图床上传。"""
    from nonebot_plugin_alconna import Text
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    for level in (1, 3, 7):
        patched_image_renderer["markdown"] = None
        message, _ = await build_markdown_message("user", _make_choice_question(level=level), 0, 0, 0, 0)
        content = next(segment for segment in message if isinstance(segment, Text)).text
        assert "1 + 2 = ?" in content
        assert "\n\n## 请选择答案\n\n" in content
        assert "A. 1\nB. 2\nC. 3" in content
        assert _FAKE_IMAGE_MARKDOWN not in content
        assert patched_image_renderer["markdown"] is None


@pytest.mark.asyncio
async def test_question_card_wraps_latex_options_in_math_mode(patched_image_renderer: dict[str, Any]) -> None:
    """L5 的裸 LaTeX 选项应包进 $...$（md_to_pic 只渲染该形式），纯数字选项保持原样。"""
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    question = _make_choice_question(level=5)
    question["question"]["options"] = ["x_{1} = \\frac{1}{2}", "-3"]

    await build_markdown_message("user", question, 0, 0, 0, 0)
    markdown: str = patched_image_renderer["markdown"]
    assert "A. $x_{1} = \\frac{1}{2}$  \nB. -3" in markdown


@pytest.mark.asyncio
async def test_question_card_falls_back_to_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """图床不可用时 L5 的题目信息应回退为纯文本，保证题目卡片仍可发送。"""
    from nonebot_plugin_alconna import Text
    from nonebot_plugin_quick_math.utils import question as question_module
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    async def failing_create_image_markdown(_data: bytes, **_kwargs: object) -> str:
        raise RuntimeError("S3 图床未配置")

    monkeypatch.setattr(question_module, "create_image_markdown", failing_create_image_markdown)

    message, _ = await build_markdown_message("user", _make_choice_question(level=5), 0, 0, 0, 0)
    content = next(segment for segment in message if isinstance(segment, Text)).text
    assert "1 + 2 = ?" in content
    assert "\n\n## 请选择答案\n\n" in content
    # 回退的纯文本交给 QQ markdown 渲染，用普通换行分隔选项即可
    assert "A. 1\nB. 2\nC. 3" in content


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


# ---------- 选项按钮回传选项字母（加快判定） ----------


@pytest.mark.asyncio
async def test_question_card_option_buttons_show_letters_for_image_level() -> None:
    """L5 的选项原文已渲染进图片，按钮内容应为字母 A/B/C。"""
    from nonebot_plugin_alconna import Keyboard
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    question = _make_choice_question(level=5)
    message, _ = await build_markdown_message("user", question, 0, 0, 0, 0, "qq_openid")
    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert [button.label for button in keyboard.children] == ["A", "B", "C"]
    assert [button.text for button in keyboard.children] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_question_card_option_buttons_keep_text_for_other_levels() -> None:
    """其余等级的选项仍以文本显示在卡片里，按钮保留选项原文，但回传字母。"""
    from nonebot_plugin_alconna import Keyboard
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    message, _ = await build_markdown_message("user", _make_choice_question(level=1), 0, 0, 0, 0, "qq_openid")
    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert [button.label for button in keyboard.children] == ["1", "2", "3"]
    assert [button.text for button in keyboard.children] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_button_letter_answers_without_slow_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    """点击正确选项按钮（回传字母）应直接答对，且不把字母送进慢速判定函数。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.types import ReplyType
    from nonebot_plugin_quick_math.utils import message as message_module
    from nonebot_plugin_quick_math.utils.question import with_option_letters

    question, calls = _make_recorded_verify("3")
    question = with_option_letters(question)

    async def prompt_stub(_message: UniMessage, _user_id: str, **_kwargs: object) -> str:
        return "c"

    monkeypatch.setattr(message_module, "prompt", prompt_stub)

    assert await message_module.wait_answer(question, UniMessage(), "user") is ReplyType.RIGHT
    # 字母被翻译为选项原文后再判定，慢速判定函数从未收到单个字母
    assert calls == ["3"]


@pytest.mark.asyncio
async def test_button_letter_answers_accepted_by_generator_questions() -> None:
    """真实题目生成器（L1）下，选项按钮回传的字母同样应被判定为正确。"""
    from nonebot_plugin_quick_math.utils.generator.levels import l1
    from nonebot_plugin_quick_math.utils.question import with_option_letters

    letters = "ABCDEFGHIJKL"
    for _ in range(20):
        data = await l1.generate_question("user")
        options = data.get("options") or []
        assert len(options) > 1
        wrapped = with_option_letters({"question": data, "max_point": 10, "level": 1, "limit_in_sec": 5})
        for index, option in enumerate(options):
            # 每个选项：字母答案与选项原文答案的判定结果必须一致
            by_letter = await wrapped["question"]["answer"](letters[index])
            by_text = await data["answer"](option)
            assert by_letter is by_text


@pytest.mark.asyncio
async def test_button_letter_answers_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """用户手输选项字母时应忽略大小写与首尾空白。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.types import ReplyType
    from nonebot_plugin_quick_math.utils import message as message_module
    from nonebot_plugin_quick_math.utils.question import with_option_letters

    for typed in ("B", "b", " b "):
        question, calls = _make_recorded_verify("2")
        question = with_option_letters(question)

        async def prompt_stub(_message: UniMessage, _user_id: str, _typed: str = typed, **_kwargs: object) -> str:
            return _typed

        monkeypatch.setattr(message_module, "prompt", prompt_stub)
        assert await message_module.wait_answer(question, UniMessage(), "user") is ReplyType.RIGHT
        assert calls == ["2"]


@pytest.mark.asyncio
async def test_wrong_button_letter_answers_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    """点击错误选项按钮（回传字母）应判定为错误，而不是重试耗尽。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.types import ReplyType
    from nonebot_plugin_quick_math.utils import message as message_module
    from nonebot_plugin_quick_math.utils.question import with_option_letters

    question, calls = _make_recorded_verify("3")
    question = with_option_letters(question)

    async def prompt_stub(_message: UniMessage, _user_id: str, **_kwargs: object) -> str:
        return "A"

    monkeypatch.setattr(message_module, "prompt", prompt_stub)

    assert await message_module.wait_answer(question, UniMessage(), "user") is ReplyType.WRONG
    assert calls == ["1", "1"]


@pytest.mark.asyncio
async def test_typed_option_text_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """用户手动输入选项原文（而非字母）时行为保持不变。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.types import ReplyType
    from nonebot_plugin_quick_math.utils import message as message_module
    from nonebot_plugin_quick_math.utils.question import with_option_letters

    question, calls = _make_recorded_verify("3")
    question = with_option_letters(question)

    async def prompt_stub(_message: UniMessage, _user_id: str, **_kwargs: object) -> str:
        return "3"

    monkeypatch.setattr(message_module, "prompt", prompt_stub)

    assert await message_module.wait_answer(question, UniMessage(), "user") is ReplyType.RIGHT
    assert calls == ["3"]


@pytest.mark.asyncio
async def test_letter_beyond_options_delegates_to_original(monkeypatch: pytest.MonkeyPatch) -> None:
    """超出选项范围的字母（如 3 个选项却输入 D）应原样交给原始判定函数。"""
    from nonebot_plugin_alconna import UniMessage
    from nonebot_plugin_quick_math.types import ReplyType
    from nonebot_plugin_quick_math.utils import message as message_module
    from nonebot_plugin_quick_math.utils.question import with_option_letters

    question, calls = _make_recorded_verify("D")
    question = with_option_letters(question)

    async def prompt_stub(_message: UniMessage, _user_id: str, **_kwargs: object) -> str:
        return "D"

    monkeypatch.setattr(message_module, "prompt", prompt_stub)

    assert await message_module.wait_answer(question, UniMessage(), "user") is ReplyType.RIGHT
    assert calls == ["D"]


@pytest.mark.asyncio
async def test_non_choice_question_delegates_to_original() -> None:
    """无选项（非选择题）的题目不应被包装，判定函数保持原样。"""
    from nonebot_plugin_quick_math.utils.question import with_option_letters

    async def answer_fn(_: str) -> bool:
        return True

    question = {
        "question": {"question": "1 + 1 = ?", "answer": answer_fn},
        "max_point": 10,
        "level": 1,
        "limit_in_sec": 5,
    }
    assert with_option_letters(question)["question"]["answer"] is answer_fn


@pytest.mark.asyncio
async def test_non_qq_adapter_questions_keep_original_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 QQ 官方机器人（图片题目）不携带选项按钮，答案判定应保持原样。"""
    from nonebot.adapters.console import Bot as ConsoleBot
    from nonebot_plugin_quick_math.utils import question as question_module

    raw = _make_choice_question()

    async def generate_question(_user_id: str, _level: int) -> dict[str, Any]:
        return raw

    async def generate_image(*_args: object, **_kwargs: object) -> bytes:
        return b""

    monkeypatch.setattr(question_module, "generate_question", generate_question)
    monkeypatch.setattr(question_module, "generate_image", generate_image)

    _, question = await question_module.get_question(ConsoleBot.__new__(ConsoleBot), 1, "user", 0, 0, 0, 0)
    assert question["question"]["answer"] is raw["question"]["answer"]


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
