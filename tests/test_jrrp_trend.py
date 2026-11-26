"""``/jrrp t`` 人品走势图的渲染回归测试。

背景（PR #1601 的 E2E 报告「发现 2」）：``ax.plot(..., markerfacecolor=point_colors)``
把「每个点一个颜色」的颜色列表传给了只接受单个颜色的参数，matplotlib 在 ``savefig``
时按 RGBA 序列解析并抛 ``ValueError``，聊天侧一条消息都收不到（静默失败）。

修好后折线不再带 marker，圆点交给支持颜色列表的 ``ax.scatter`` 逐点绘制。
"""

from datetime import UTC, datetime, timedelta

import pytest

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 LangHelper.text，避免依赖数据库里的语言文本（插件导入必须在函数内）"""
    from nonebot_plugin_jrrp.trend import lang

    async def fake_text(key: str, _user_id: str, *_args: object, **_kwargs: object) -> str:
        return f"text::{key}"

    monkeypatch.setattr(lang, "text", fake_text)


@pytest.mark.asyncio
async def test_render_trend_with_multiple_points() -> None:
    """多点走势图能正常渲染成 PNG（逐点配色不再触发 RGBA 解析错误）"""
    from nonebot_plugin_jrrp.trend import render_luck_trend_chart

    dates = [datetime.now(UTC).date() - timedelta(days=offset) for offset in range(6, -1, -1)]
    values = [0, 5, 33, 57, 71, 85, 100]

    data = await render_luck_trend_chart("trend-user", dates, values, 7, 50.1)

    assert data.startswith(_PNG_MAGIC)


@pytest.mark.asyncio
async def test_render_trend_with_single_point() -> None:
    """只有一个数据点（列表颜色长度为 1）时同样能渲染"""
    from nonebot_plugin_jrrp.trend import render_luck_trend_chart

    data = await render_luck_trend_chart("trend-user", [datetime.now(UTC).date()], [120], 7, 120.0)

    assert data.startswith(_PNG_MAGIC)


@pytest.mark.asyncio
async def test_render_trend_without_data() -> None:
    """没有走势数据时返回「暂无数据」占位图而不是抛异常"""
    from nonebot_plugin_jrrp.trend import render_luck_trend_chart

    data = await render_luck_trend_chart("trend-user", [], [], 7, 0.0)

    assert data.startswith(_PNG_MAGIC)
