#  Moonlark - A new ChatBot
#  Copyright (C) 2026  Moonlark Development Team
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
# ##############################################################################
import asyncio


def _panel():
    from nonebot_plugin_larkhelp import panel

    return panel


def test_fit_text_ladder():
    """长描述先降字号，降到最小仍放不下才截断加省略号"""
    panel = _panel()
    text = "查看当前是梁文峰还是梁文谷" * 5
    result, size, truncated = panel.fit_text(text, panel.DESC_LADDER, panel.DESC_W)
    assert size == panel.DESC_LADDER[-1]
    assert truncated
    assert result.endswith("…")
    assert panel.text_width(result, size) <= panel.DESC_W
    # 正常描述不触发阶梯
    result2, size2, truncated2 = panel.fit_text("查看当前是梁文峰还是梁文谷", panel.DESC_LADDER, panel.DESC_W)
    assert size2 == panel.DESC_LADDER[0] and not truncated2 and result2 == "查看当前是梁文峰还是梁文谷"


def test_pack_columns_balance():
    """分类块灌进各栏：允许跨栏续排，内容不重不漏，两栏都非空"""
    panel = _panel()
    blocks = []
    for i in range(4):
        blocks.append(
            panel.Block(
                "cat",
                [panel.Cmd(f"cmd-{i}-{j}", f"说明 {j}", "new") for j in range(18 + 3 * i)],
            )
        )
    columns = panel.pack_columns(blocks, 2)
    assert len(columns) == 2
    heights = [sum(panel.CAT_H + len(p.rows) * panel.ROW_H for p in col) for col in columns]
    # 高度差不至于一边全空（续排算法保证内容大体均衡）
    assert all(h > 0 for h in heights)
    assert abs(heights[0] - heights[1]) < max(b.height for b in blocks)
    # 跨栏续排的 piece 带 cont 标记（栏首若是续排同样标记）
    pieces = [p for col in columns for p in col]
    assert not all(p.cont for p in pieces)
    assert any(p.cont for p in pieces)
    # 内容不重不漏
    total = sum(len(p.rows) for p in pieces)
    assert total == sum(len(b.rows) for b in blocks)
    # 没有空 piece（不会画出「0 条」的分类头）
    assert all(p.rows for p in pieces)


def test_apply_hot_data_deduplicate():
    """热门前三名从下方列表剔除，下线指令跳过，分类被剔空则整块不渲染"""
    panel = _panel()
    rows = [
        panel.Cmd("sign", "签到", "game"),
        panel.Cmd("jrrp", "今日人品", "game"),
        panel.Cmd("help", "命令帮助", "tools"),
        panel.Cmd("alias", "指令别名", "tools"),
        panel.Cmd("offline", "已下线", "new"),
    ]
    shown, hot, by_name = panel.apply_hot_data(rows, [("sign", 100), ("jrrp", 90), ("not-in-help", 80), ("help", 70)])
    assert [n for n, _ in hot] == ["sign", "jrrp", "help"]
    shown_names = {c.name for c in shown}
    assert {"sign", "jrrp", "help"}.isdisjoint(shown_names)
    assert shown_names == {"alias", "offline"}
    # 游戏类被剔空：不进分类块，整块不渲染
    blocks = panel.build_category_blocks(shown)
    cats = {b.cat for b in blocks if b.rows}
    assert "game" not in cats
    assert set(cats) == {"tools", "new"}


def test_hot_provider_graceful_degradation():
    """未注册 provider 或 provider 报错时返回空热门，面板省略热门分区而不是报错"""
    panel = _panel()
    saved = panel._hot_provider

    async def broken():
        raise RuntimeError("boom")

    panel.register_hot_provider(broken)
    try:
        assert asyncio.run(panel._get_hot()) == []
    finally:
        if saved is None:
            panel._hot_provider = None
        else:
            panel.register_hot_provider(saved)
    assert asyncio.run(panel._get_hot()) == []


def test_no_hot_provider_skips_band():
    """无热门数据时版面里没有热门条带预留"""
    panel = _panel()
    rows = [panel.Cmd("a", "A", "tools"), panel.Cmd("b", "B", "game")]
    texts = panel.PanelTexts(
        title="",
        eyebrow="",
        subtitle="",
        hint="",
        badge="",
        hot_title="",
        hot_note="",
        hot_count="{} 次",
        row_count="{} 条",
        cont="‹{}›（续）",
        footer="",
        logo_alt="",
        logo_alt_sub="",
        cat_names={"tools": "t", "game": "g"},
    )
    img = panel.draw_panel(rows, [], texts, None)
    # 画布高度比有热门条带时矮 HOT_H；两分类各占一个分类头 + 一行
    assert (
        img.height == (panel.PAD + panel.HEADER_H + 26 + panel.CAT_H + panel.ROW_H + 24 + panel.FOOTER_H) * panel.SCALE
    )


def test_cache_roundtrip_and_ttl():
    panel = _panel()
    key = ("zh_hans", "sig")
    panel.cache_set(key, b"data")
    assert panel.cache_get(key) == b"data"
    panel._PANEL_CACHE[key] = (0.0, b"stale")
    assert panel.cache_get(key) is None


class _FakeHelp:
    """CommandHelp 的最小替身"""

    def __init__(self, plugin: str, category: str):
        self.plugin = plugin
        self.category = category
        self.description = "x.description"
        self.details = "x.details"
        self.usages = []


_LAND_KEYS = {
    "panel.title": "指令手册",
    "panel.eyebrow": "MOONLARK · LARKHELP",
    "panel.subtitle": "sub",
    "panel.hint": "hint",
    "panel.badge": "条指令",
    "panel.hot_title": "热门指令",
    "panel.hot_note": "note",
    "panel.hot_count": "{} 次",
    "panel.row_count": "{} 条",
    "panel.cont": "‹{}›（续）",
    "panel.footer": "footer",
    "panel.logo_alt": "L",
    "panel.logo_alt_sub": "s",
    "list.category.tools": "实用工具",
    "list.category.game": "游戏与娱乐",
}


async def test_render_end_to_end(monkeypatch):
    """mock 掉语言数据后，渲染入口应产出可解码的 WebP"""
    import io

    from PIL import Image

    panel = _panel()
    monkeypatch.setattr(panel, "_hot_provider", None)

    async def fake_rows(user_id, help_list):
        return [
            panel.Cmd("alias", "指令别名", "tools"),
            panel.Cmd("sign", "签到", "game"),
            panel.Cmd("secret", "隐藏", "superuser"),
        ]

    async def fake_lang(user_id):
        return "zh_hans"

    async def fake_text(key, user_id, *args):
        return _LAND_KEYS.get(key, key)

    async def fake_hot():
        return []

    monkeypatch.setattr(panel, "_collect_rows", fake_rows)
    monkeypatch.setattr(panel, "_get_lang", fake_lang)
    monkeypatch.setattr(panel, "_lang_text", fake_text)
    monkeypatch.setattr(panel, "_get_hot", fake_hot)

    data = await panel.render_help_panel(
        "test-user",
        {
            "alias": _FakeHelp("plugin_a", "tools"),
            "sign": _FakeHelp("plugin_b", "game"),
            "secret": _FakeHelp("plugin_a", "superuser"),
        },
    )
    assert isinstance(data, bytes) and data[:4] == b"RIFF"
    img = Image.open(io.BytesIO(data))
    assert img.format == "WEBP"
    assert img.width == panel.W


async def test_render_uses_provider_and_deduplicates(monkeypatch):
    """provider 注入的热门指令进入条带，并从下方列表移出"""
    import io

    from PIL import Image

    panel = _panel()
    fake_help_list = {
        "alias": _FakeHelp("plugin_a", "tools"),
        "sign": _FakeHelp("plugin_b", "game"),
        "help_cmd": _FakeHelp("plugin_a", "tools"),
    }

    async def fake_rows(user_id, help_list):
        return [
            panel.Cmd("alias", "指令别名", "tools"),
            panel.Cmd("sign", "签到", "game"),
            panel.Cmd("help_cmd", "帮助", "tools"),
        ]

    async def fake_lang(user_id):
        return "zh_hans"

    async def fake_text(key, user_id, *args):
        return _LAND_KEYS.get(key, key)

    async def fake_hot():
        return [("sign", 100), ("gone", 90)]

    monkeypatch.setattr(panel, "_collect_rows", fake_rows)
    monkeypatch.setattr(panel, "_get_lang", fake_lang)
    monkeypatch.setattr(panel, "_lang_text", fake_text)
    monkeypatch.setattr(panel, "_get_hot", fake_hot)
    panel._PANEL_CACHE.clear()

    data = await panel.render_help_panel("lang-test-user-2", fake_help_list)
    # 缓存键含 hot_sig：同 lang 下带热门与不带热门的缓存互不干扰
    other_key = ("zh_hans", "")
    panel.cache_set(other_key, b"base")
    assert panel.cache_get(("zh_hans", "sign:100")) is not None
    img = Image.open(io.BytesIO(data))
    assert img.format == "WEBP"
