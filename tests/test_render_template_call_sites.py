"""``render_template`` 调用约定的回归测试。

背景：``render_template`` 曾经在 ``cache`` 与 ``viewport`` 之间有一个 ``resize``
参数（对截图做 75% 缩放）。``nonebot_plugin_larkhelp`` 按位置传了
``cache=True, resize=True``。``resize`` 被删除后（渲染统一转 WebP），那两个 ``True``
里的第二个就落到了 ``viewport`` 上，于是布尔值被原样交给 playwright：

    playwright._impl._errors.Error: Browser.new_page: viewport: expected object, got boolean

触发点是 bot 连接时的 ``setup_cache()``——它用
``mlsid::--lang={lang};--theme={theme};--ignore-cache=y`` 预热每个 creator 模板的缓存，
所以 ``/help`` 与 ``/menu`` 在启动时就已经渲染失败（``--ignore-cache=y`` 只跳过读取
已有缓存，仍然会真的渲染一次）。

这里锁住两件事：可选参数只能按关键字传递（错位会立刻抛 ``TypeError`` 而不是静默换义），
以及仓库内所有调用点都遵守这个约定。
"""

import ast
import inspect
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
_REQUIRED_POSITIONAL = ("name", "title", "user_id", "templates")
_OPTIONAL_PARAMS = ("keys", "cache", "viewport", "background_url")


def _iter_call_sites() -> list[tuple[Path, int, ast.Call]]:
    """遍历 src/ 下所有 ``render_template(...)`` 调用点"""
    found: list[tuple[Path, int, ast.Call]] = []
    for path in sorted(_SRC_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "render_template":
                found.append((path, node.lineno, node))
    return found


def test_optional_params_are_keyword_only() -> None:
    """keys / cache / viewport / background_url 必须是 keyword-only"""
    from nonebot_plugin_render.render import render_template

    parameters = inspect.signature(render_template).parameters
    for name in _REQUIRED_POSITIONAL:
        assert parameters[name].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name
    for name in _OPTIONAL_PARAMS:
        assert parameters[name].kind is inspect.Parameter.KEYWORD_ONLY, name


def test_positional_optional_args_raise_type_error() -> None:
    """按位置传可选参数（旧写法）必须立刻报错，而不是被当成 viewport"""
    from nonebot_plugin_render.render import render_template

    with pytest.raises(TypeError):
        # 等价于旧的 render_template(name, title, user_id, templates, keys, cache, viewport)
        render_template("t.jinja", "t", "u", {}, {}, True, True)


def test_no_call_site_passes_optional_args_positionally() -> None:
    """src/ 下所有调用点都不得按位置传可选参数（这正是线上崩溃的成因）"""
    call_sites = _iter_call_sites()
    assert call_sites, "没有找到任何 render_template 调用点，扫描逻辑可能已失效"

    offenders = [
        f"{path.relative_to(_SRC_DIR.parent)}:{lineno}（传了 {len(node.args)} 个位置参数）"
        for path, lineno, node in call_sites
        if len(node.args) > len(_REQUIRED_POSITIONAL)
    ]
    assert not offenders, "render_template 的可选参数必须用关键字传递：" + "; ".join(offenders)


def test_no_call_site_passes_boolean_viewport() -> None:
    """viewport 只能传字典或 None：布尔值会被 playwright 拒绝（Browser.new_page: viewport: expected object）"""
    offenders = []
    for path, lineno, node in _iter_call_sites():
        for keyword in node.keywords:
            if keyword.arg != "viewport":
                continue
            # None 表示回落到 render_viewport 配置，合法；常量（True/False/数字/字符串）都非法
            if isinstance(keyword.value, ast.Constant) and keyword.value.value is not None:
                offenders.append(f"{path.relative_to(_SRC_DIR.parent)}:{lineno}={keyword.value.value!r}")
    assert not offenders, "viewport 必须是字典（或省略以使用 render_viewport 配置）：" + "; ".join(offenders)


@pytest.fixture
def larkhelp_render_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """记录 larkhelp 调用 render_template 的原始位置/关键字参数

    插件导入必须在 fixture 内部进行（collection 阶段 nonebot 尚未初始化）。"""
    import nonebot_plugin_larkhelp.__main__ as module
    from nonebot_plugin_larklang.__main__ import LangHelper

    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def fake_render_template(*args: Any, **kwargs: Any) -> bytes:
        calls.append((args, kwargs))
        return b"webp-bytes"

    async def fake_text(self: LangHelper, key: str, _user_id: str, *_args: object) -> str:
        return f"lang::{key}"

    monkeypatch.setattr(module, "render_template", fake_render_template)
    monkeypatch.setattr(LangHelper, "text", fake_text)
    monkeypatch.setattr(module, "get_templates", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "get_menu_templates", AsyncMock(return_value=[]))
    monkeypatch.setattr(module, "get_random_command", AsyncMock(return_value={}))
    return calls


@pytest.mark.asyncio
async def test_larkhelp_help_render_uses_keywords(
    larkhelp_render_calls: list[tuple[tuple[Any, ...], dict[str, Any]]],
) -> None:
    """/help 的渲染只传 4 个位置参数，cache 用关键字，且绝不出现 viewport"""
    import nonebot_plugin_larkhelp.__main__ as module

    await module.render("mlsid::--lang=zh_hans;--theme=default;--ignore-cache=y")

    assert len(larkhelp_render_calls) == 1
    args, kwargs = larkhelp_render_calls[0]
    assert args[0] == "help.html.jinja"
    assert len(args) == len(_REQUIRED_POSITIONAL), f"位置参数过多，viewport 位置被布尔值顶掉了：{args!r}"
    assert kwargs["cache"] is True
    assert "viewport" not in kwargs
    assert not any(isinstance(value, bool) for value in args)


@pytest.mark.asyncio
async def test_larkhelp_menu_render_uses_keywords(
    larkhelp_render_calls: list[tuple[tuple[Any, ...], dict[str, Any]]],
) -> None:
    """/menu 的渲染同样不能把 cache 的位置让给 viewport"""
    import nonebot_plugin_larkhelp.__main__ as module

    await module.render_menu("10")

    assert len(larkhelp_render_calls) == 1
    args, kwargs = larkhelp_render_calls[0]
    assert args[0] == "menu.html.jinja"
    assert len(args) == len(_REQUIRED_POSITIONAL), f"位置参数过多，viewport 位置被布尔值顶掉了：{args!r}"
    assert kwargs["cache"] is True
    assert "viewport" not in kwargs
