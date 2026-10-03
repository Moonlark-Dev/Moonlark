"""nonebot_plugin_jrrp 人品排行卡片的渲染回归测试。

背景：``jrrp_rank.html.jinja`` / ``jrrp_rank_reverse.html.jinja`` 此前在页面里跑一段
JS，用 ``offsetHeight`` 给三张卡片写死 ``height`` / ``paddingTop`` 来对齐领奖台。
卡片本身是块级容器、内容会溢出（冠军卡片内容约 271px 却被写成 201px 高），于是冠军
卡片的内容盖住自己的背景色、用户摘要行被挤成两行、整行卡片溢出容器——也就是
``/jrrp r`` 渲染出来的排版错乱。

修好后改为纯 CSS 领奖台（flex 等分三列 + ``align-items: flex-end`` + 第 2/3 名
``margin-top`` 拉开高度差），冠军分值也回到服务端渲染。这里断言模板不再依赖运行时
脚本撑高卡片，避免有人又把 JS 那套加回来。

渲染使用与 ``nonebot_plugin_render.render`` 相同的 Jinja 环境配置，纯模板渲染、
不需要浏览器。
"""

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "src" / "templates"


def _render(template_name: str, **kwargs: object) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = env.get_template(template_name)
    return template.render(
        base="base/default.html.jinja",
        main_title="今日人品排行",
        footer="由 Moonlark & nonebot_plugin_jrrp 生成",
        background_url="",
        **kwargs,
    )


def _podium_context() -> dict[str, object]:
    """两张模板共用同一份上下文：幸运星读 text.title，倒霉蛋读 text.reverse_title"""
    return {
        "text": {"title": "今日幸运星", "reverse_title": "今日倒霉蛋", "unregistered": "未注册用户无法参与排名"},
        "luckiest_1": {"user_id": "2915495930", "value": 100, "avatar": None, "nickname": "StarWorld"},
        "luckiest_2": {
            "user_id": "6B24BC303D08F9E0053F81E16860BBD7",
            "value": 85,
            "avatar": None,
            "nickname": "slwyts",
        },
        "luckiest_3": {
            "user_id": "7B5A4E84D2BE96A7AC209B2BB64DD428",
            "value": 70,
            "avatar": None,
            "nickname": "yukino",
        },
        "user": {"index": 12, "nickname": "XiaoDeng3386", "data": 85, "info": "领先 76.9% 的用户"},
    }


@pytest.mark.parametrize("template_name", ["jrrp_rank.html.jinja", "jrrp_rank_reverse.html.jinja"])
def test_podium_layout_does_not_use_runtime_script(template_name: str) -> None:
    """领奖台必须由 CSS 布局决定，不能再靠脚本给卡片写死高度"""
    source = (_TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
    html = _render(template_name, **_podium_context())

    # 模板自身不应再内联脚本（基模板引入 MDB 的外链 script 不受影响）
    assert "<script" not in source.lower()
    # 脚本那套写死高度的痕迹不应再出现
    assert "offsetHeight" not in source
    assert "offsetHeight" not in html
    assert "paddingTop" not in html
    assert "style.height" not in html
    assert "innerHTML" not in html
    # 三列等分 + 第 2/3 名下移构成领奖台
    assert 'class="podium"' in html
    assert html.count('class="card luckiest luckiest-low"') == 2


@pytest.mark.parametrize("template_name", ["jrrp_rank.html.jinja", "jrrp_rank_reverse.html.jinja"])
def test_podium_renders_every_slot_server_side(template_name: str) -> None:
    """三张卡片、冠军分值、用户摘要都应在服务端直接渲染出来"""
    html = _render(template_name, **_podium_context())

    for nickname in ("StarWorld", "slwyts", "yukino"):
        assert nickname in html
    # 冠军分值此前由页面脚本追加，现在必须是模板直接输出
    assert '<p class="value">100</p>' in html
    # 用户摘要行（名次、昵称、分值、领先比例）
    assert "12. XiaoDeng3386" in html
    assert "领先 76.9% 的用户" in html


def test_podium_handles_missing_slots_and_avatars() -> None:
    """少于三名用户、且没有头像时不应报错，也不该出现空的 img 标签"""
    context = _podium_context()
    context["luckiest_2"] = {"user_id": "", "value": "", "avatar": None, "nickname": ""}
    context["luckiest_3"] = {"user_id": "", "value": "", "avatar": None, "nickname": ""}
    context["user"] = None

    html = _render("jrrp_rank.html.jinja", **context)

    assert 'class="podium"' in html
    assert "<img" not in html
    # 未注册用户走 unregistered 文案
    assert "未注册用户无法参与排名" in html
