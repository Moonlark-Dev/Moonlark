"""L8 矩阵乘法题目的回归测试。

覆盖的要点：

- 题目与所有选项都是 LaTeX ``pmatrix``，正确答案确实是题面中 A 与 B 的乘积；
- 干扰项覆盖常见错误：转置、哈达玛积（对应元素相乘）、A·Bᵀ、漏加项、
  列下标错位、顺序颠倒（B·A）与维度不符的矩阵；
- L8 在 QQ 官方机器人下与 L5 一样把题面和选项渲染成图片，按钮只显示字母；
- 素材库不可用时 ``latex_to_plain`` 能把矩阵转成可读的 ``[a, b; c, d]``；
- 普通/禅/PvP 会话的等级上限跟随 ``GENERATOR_LIST``，不再写死为 7。
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

_LANG_FILE = Path(__file__).resolve().parents[1] / "src" / "lang" / "zh_hans" / "quick_math.yaml"

_PMATRIX_PATTERN = re.compile(r"\\begin\{pmatrix\}(.*?)\\end\{pmatrix\}", re.DOTALL)

# 素材库返回的 markdown 图片代码（含 QQ 需要的宽高标注）
_FAKE_IMAGE_MARKDOWN = "![text #100px #50px](https://example.com/question.jpg)"

# build_markdown_message 需要 QQ 官方机器人实例；本文件里素材上传总被替换为假实现
_FAKE_BOT: Any = object()


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


def _parse_matrix(latex: str) -> list[list[int]]:
    """把 ``pmatrix`` 解析回整数矩阵。"""
    match = _PMATRIX_PATTERN.fullmatch(latex)
    assert match is not None, latex
    rows = [row for row in re.split(r"\\\\", match.group(1)) if row.strip()]
    return [[int(cell) for cell in row.split("&")] for row in rows]


def _multiply(left: list[list[int]], right: list[list[int]]) -> list[list[int]]:
    return [
        [sum(left[i][k] * right[k][j] for k in range(len(right))) for j in range(len(right[0]))]
        for i in range(len(left))
    ]


@pytest.mark.asyncio
async def test_l8_answer_is_the_matrix_product() -> None:
    """选项中的正确答案必须等于题面 A 与 B 的乘积。"""
    from nonebot_plugin_quick_math.utils.generator.levels import l8
    from nonebot_plugin_quick_math.utils.generator.levels.options import OPTION_LETTERS

    for _ in range(30):
        question = await l8.generate_question("user")
        left_latex, right_latex = _PMATRIX_PATTERN.findall(question["question"])
        expected = _multiply(
            _parse_matrix(f"\\begin{{pmatrix}}{left_latex}\\end{{pmatrix}}"),
            _parse_matrix(f"\\begin{{pmatrix}}{right_latex}\\end{{pmatrix}}"),
        )
        correct_option = question["options"][OPTION_LETTERS.index(question["answer"])]
        assert _parse_matrix(correct_option) == expected


@pytest.mark.asyncio
async def test_l8_options_are_distinct_matrices() -> None:
    """每个选项都应是合法的矩阵，且选项之间不重复。"""
    from nonebot_plugin_quick_math.utils.generator.levels import l8
    from nonebot_plugin_quick_math.utils.generator.levels.options import OPTION_LETTERS

    for _ in range(30):
        question = await l8.generate_question("user")
        assert len(question["options"]) >= 2
        assert all(_PMATRIX_PATTERN.fullmatch(option) for option in question["options"])
        assert len(set(question["options"])) == len(question["options"])
        assert OPTION_LETTERS.index(question["answer"]) < len(question["options"])


def test_l8_distractors_cover_common_mistakes() -> None:
    """干扰项池应覆盖转置、哈达玛积、A·Bᵀ、漏加项、错位、颠倒顺序与错误维度。"""
    from nonebot_plugin_quick_math.utils.generator.levels import l8

    left = [[1, 2], [3, 4]]
    right = [[5, 6], [7, 8]]
    answer = _multiply(left, right)
    pool = l8.build_distractors(left, right, answer)
    latex_pool = {l8.matrix_latex(matrix) for matrix in pool}

    assert l8.matrix_latex([[19, 43], [22, 50]]) in latex_pool  # 转置
    assert l8.matrix_latex([[5, 12], [21, 32]]) in latex_pool  # 对应元素相乘
    assert l8.matrix_latex([[17, 23], [39, 53]]) in latex_pool  # A·Bᵀ
    assert l8.matrix_latex([[5, 6], [15, 18]]) in latex_pool  # 漏加项
    assert l8.matrix_latex([[22, 19], [50, 43]]) in latex_pool  # 列错位
    assert l8.matrix_latex([[23, 34], [31, 46]]) in latex_pool  # B·A
    # 维度错误项：2×2 的答案混入一个 3×2 的矩阵
    assert any(len(matrix) == 3 and len(matrix[0]) == 2 for matrix in pool)


def test_latex_to_plain_renders_pmatrix() -> None:
    """回退纯文本时矩阵应转换为可读的 [a, b; c, d] 形式。"""
    from nonebot_plugin_quick_math.utils.latex import latex_to_plain

    assert latex_to_plain("$$\\begin{pmatrix} 19 & 22 \\\\ 43 & 50 \\end{pmatrix}$$") == "[19, 22; 43, 50]"
    assert (
        latex_to_plain(
            "$$A = \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix},\\quad "
            "B = \\begin{pmatrix} 5 & 6 \\\\ 7 & 8 \\end{pmatrix}$$",
        )
        == "A = [1, 2; 3, 4], B = [5, 6; 7, 8]"
    )


@pytest.fixture
def patched_image_renderer(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """拦截题目信息渲染与素材上传，避免测试依赖浏览器与 QQ 素材库。"""
    from nonebot_plugin_quick_math.utils import question as question_module

    captured: dict[str, Any] = {"markdown": None, "image": None}

    async def fake_md_to_pic(markdown: str, **_kwargs: object) -> bytes:
        captured["markdown"] = markdown
        return b"fake-image"

    async def fake_create_image_markdown(data: bytes, *_args: object, **_kwargs: object) -> str:
        captured["image"] = data
        return _FAKE_IMAGE_MARKDOWN

    monkeypatch.setattr(question_module, "md_to_pic", fake_md_to_pic)
    monkeypatch.setattr(question_module, "create_image_markdown", fake_create_image_markdown)
    return captured


def _make_l8_question() -> dict[str, Any]:
    return {
        "question": {
            "question": "计算下列矩阵的乘积：\n\n$$A = \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix},\\quad B = \\begin{pmatrix} 5 & 6 \\\\ 7 & 8 \\end{pmatrix}$$",
            "options": [
                "\\begin{pmatrix} 19 & 22 \\\\ 43 & 50 \\end{pmatrix}",
                "\\begin{pmatrix} 19 & 43 \\\\ 22 & 50 \\end{pmatrix}",
            ],
            "answer": "A",
        },
        "max_point": 80,
        "level": 8,
        "limit_in_sec": 90,
    }


@pytest.mark.asyncio
async def test_l8_question_card_renders_matrices_as_image(patched_image_renderer: dict[str, Any]) -> None:
    """L8 的题面与选项应渲染为图片，按钮只显示选项字母。"""
    from nonebot_plugin_alconna import Keyboard, Text
    from nonebot_plugin_quick_math.utils.question import build_markdown_message

    message, _ = await build_markdown_message(_FAKE_BOT, "user", _make_l8_question(), 0, 0, 0, 0, "qq_openid")
    content = next(segment for segment in message if isinstance(segment, Text)).text
    assert f"## 题目信息\n\n{_FAKE_IMAGE_MARKDOWN}" in content
    # 矩阵原文不应直接出现在 QQ markdown 卡片里
    assert "\\begin{pmatrix}" not in content
    # 题目信息图片内容包含矩阵选项（包在 $...$ 中）与“请选择答案”标题
    markdown: str = patched_image_renderer["markdown"]
    assert "## 请选择答案" in markdown
    assert "A. $\\begin{pmatrix} 19 & 22 \\\\ 43 & 50 \\end{pmatrix}$" in markdown
    # 按钮文字只有选项字母，选项原文已经在图片里
    keyboard = next(segment for segment in message if isinstance(segment, Keyboard))
    assert [button.text for button in keyboard.children[:2]] == ["A", "B"]


def test_l8_is_registered_as_highest_level() -> None:
    """L8 应注册为最高等级，会话等级上限不再写死为 7。"""
    from nonebot_plugin_quick_math.utils.generator import GENERATOR_LIST, get_max_level
    from nonebot_plugin_quick_math.utils.session import QuickMathSession

    assert get_max_level() == 8
    assert 8 in GENERATOR_LIST

    session = QuickMathSession("user", None)  # type: ignore[arg-type]
    assert session.set_max_level(99) == ("random", 8)
    assert session.set_max_level(0) == ("random", 1)
