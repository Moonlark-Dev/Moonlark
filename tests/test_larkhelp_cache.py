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
"""LarkHelp 独立面板缓存与热门指令榜单后台定时更新测试。

验证目标：
1. ``nonebot_plugin_larkhelp`` 不再向 ``nonebot_plugin_render.cache`` 注册 ``@creator``，
   避免按 ``语言 × 主题``（3 × 4 = 12）在 Render 缓存目录生成重复且无用的缓存文件。
2. 面板缓存挂在 lifespan 的 ``on_ready`` 阶段清理并后台预热，仅按语言生成（如 3 个语言共 3 份），
   不同 ``.theme`` 用户共享同一语言缓存。
3. ``/help`` 命中磁盘缓存时直接返回字节，不收集全部指令文案或重跑数据库排行。
4. 定时刷新任务仅在近 7 天热门指令榜单（前三名及次数）或日期发生变化、或缓存缺失时重绘并原子替换文件。
"""

from pathlib import Path  # ruff: ignore[typing-only-standard-library-import]
from typing import Any

import pytest


class _FakeHelp:
    def __init__(self, plugin: str, category: str) -> None:
        self.plugin = plugin
        self.category = category
        self.description = "x.description"
        self.details = "x.details"
        self.usages: list[str] = []


def _lifespan() -> Any:
    from nonebot import get_driver

    return get_driver()._lifespan  # ruff: ignore[private-member-access]


def _list_file_names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.is_file())


def test_larkhelp_not_registered_in_render_creator() -> None:
    """帮助面板使用 Pillow 绘制且与主题无关，不得再注册到 Render 缓存创建器"""
    import nonebot_plugin_larkhelp.__main__  # ruff: ignore[unused-import]
    import nonebot_plugin_render.cache as render_cache

    assert "help_panel" not in render_cache.creator_functions
    assert "help.html.jinja" not in render_cache.creator_functions


def test_larkhelp_cache_hooks_and_scheduler_registered() -> None:
    """启动预热挂在 ready 阶段，且 APScheduler 注册了热门榜单定时刷新任务"""
    from nonebot_plugin_apscheduler import scheduler
    import nonebot_plugin_larkhelp.cache as cache

    lifespan = _lifespan()
    assert cache.prepare_cache in lifespan._ready_funcs  # ruff: ignore[private-member-access]
    assert cache.prepare_cache not in lifespan._startup_funcs  # ruff: ignore[private-member-access]

    job = scheduler.get_job("larkhelp_refresh_panel_cache")
    assert job is not None


@pytest.fixture
def fake_larkhelp_cache_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    import nonebot_plugin_larkhelp.cache as cache
    from nonebot_plugin_larkhelp import panel

    state: dict[str, Any] = {
        "renders": [],
        "hot": [("sign", 100), ("jrrp", 80), ("bag", 50)],
        "date": "2026-11-17",
        "help_list": {
            "sign": _FakeHelp("sign", "game"),
            "jrrp": _FakeHelp("jrrp", "game"),
            "bag": _FakeHelp("bag", "tools"),
            "alias": _FakeHelp("command_alias", "tools"),
            "secret": _FakeHelp("admin", "superuser"),
        },
    }

    async def fake_hot() -> list[tuple[str, int]]:
        return list(state["hot"])

    async def fake_render_panel(
        user_id: str,
        _help_list: dict,
        *,
        ignore_cache: bool = False,
        hot_override: list[tuple[str, int]] | None = None,
        date_override: str | None = None,
    ) -> bytes:
        state["renders"].append(
            {
                "user_id": user_id,
                "ignore_cache": ignore_cache,
                "hot": hot_override,
                "date": date_override,
            },
        )
        sig = cache.build_hot_signature(hot_override or [])
        return f"webp::{user_id}::{date_override}::{sig}".encode()

    monkeypatch.setattr(cache, "cache_dir", tmp_path)
    monkeypatch.setattr(cache, "_last_signature", None)
    monkeypatch.setattr(cache.config, "larkhelp_cache", True)
    monkeypatch.setattr(cache, "get_languages", lambda: {"en_us": None, "zh_hans": None, "zh_tw": None})
    monkeypatch.setattr(cache, "get_help_list", lambda: state["help_list"])
    monkeypatch.setattr(cache, "_current_date", lambda: state["date"])
    monkeypatch.setattr(panel, "font_available", lambda: True)
    monkeypatch.setattr(panel, "_get_hot", fake_hot)
    monkeypatch.setattr(panel, "render_help_panel", fake_render_panel)
    return state


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_larkhelp_cache_env")
async def test_prepare_cache_clears_stale_files_and_starts_warm_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nonebot_plugin_larkhelp.cache as cache

    started: list[None] = []
    monkeypatch.setattr(cache, "start_cache_warm_up", lambda: started.append(None))

    stale = tmp_path / "panel_old.webp"
    stale.write_bytes(b"stale")
    nested = tmp_path / "subdir"
    nested.mkdir()

    await cache.prepare_cache()

    assert not stale.exists()
    assert nested.is_dir()
    assert started == [None]


@pytest.mark.asyncio
async def test_prepare_cache_respects_disabled_config(
    fake_larkhelp_cache_env: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nonebot_plugin_larkhelp.cache as cache

    started: list[None] = []
    monkeypatch.setattr(cache, "start_cache_warm_up", lambda: started.append(None))
    monkeypatch.setattr(cache.config, "larkhelp_cache", False)

    stale = tmp_path / "panel_old.webp"
    stale.write_bytes(b"stale")

    await cache.prepare_cache()
    await cache.scheduled_refresh_cache()

    assert not stale.exists()
    assert not started
    assert not fake_larkhelp_cache_env["renders"]


@pytest.mark.asyncio
async def test_warm_up_creates_only_one_file_per_language_not_per_theme(
    fake_larkhelp_cache_env: dict[str, Any],
    tmp_path: Path,
) -> None:
    """3 种语言只创建 3 份缓存文件，绝不按 4 种主题膨胀为 12 份"""
    import nonebot_plugin_larkhelp.cache as cache

    await cache.warm_up_cache()

    assert _list_file_names(tmp_path) == ["panel_en_us.webp", "panel_zh_hans.webp", "panel_zh_tw.webp"]
    assert len(fake_larkhelp_cache_env["renders"]) == 3
    for lang in ("en_us", "zh_hans", "zh_tw"):
        cached = await cache.get_cache(lang)
        assert cached is not None
        assert f"--lang={lang}".encode() in cached


@pytest.mark.asyncio
async def test_scheduled_refresh_skips_when_unchanged_and_updates_on_ranking_or_date_change(
    fake_larkhelp_cache_env: dict[str, Any],
) -> None:
    """热门指令榜单与日期未变时跳过重绘；榜单次数/名次或日期变化时后台重绘更新全语言缓存"""
    import nonebot_plugin_larkhelp.cache as cache

    await cache.warm_up_cache()
    assert len(fake_larkhelp_cache_env["renders"]) == 3
    initial_zh = await cache.get_cache("zh_hans")
    assert initial_zh is not None
    assert b"sign:100|jrrp:80|bag:50" in initial_zh

    # 榜单和日期均未变化：定时任务不触发重绘
    fake_larkhelp_cache_env["renders"].clear()
    await cache.scheduled_refresh_cache()
    assert fake_larkhelp_cache_env["renders"] == []

    # 热门指令榜单发生变化（包括 superuser 指令被自动排除、新指令冲进前三）
    fake_larkhelp_cache_env["hot"] = [("secret", 999), ("jrrp", 120), ("sign", 105), ("alias", 60)]
    await cache.scheduled_refresh_cache()
    assert len(fake_larkhelp_cache_env["renders"]) == 3
    updated_zh = await cache.get_cache("zh_hans")
    assert updated_zh is not None
    assert b"jrrp:120|sign:105|alias:60" in updated_zh

    # 再次无变化：跳过
    fake_larkhelp_cache_env["renders"].clear()
    await cache.scheduled_refresh_cache()
    assert fake_larkhelp_cache_env["renders"] == []

    # 跨零点日期变化：触发更新副标题日期
    fake_larkhelp_cache_env["date"] = "2026-11-18"
    await cache.scheduled_refresh_cache()
    assert len(fake_larkhelp_cache_env["renders"]) == 3
    next_day_zh = await cache.get_cache("zh_hans")
    assert next_day_zh is not None
    assert b"2026-11-18" in next_day_zh


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_larkhelp_cache_env")
async def test_scheduled_refresh_retries_if_single_language_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单个语言渲染失败不影响其他语言落盘，且下一轮定时刷新会自动补齐缺失语言"""
    import nonebot_plugin_larkhelp.cache as cache
    from nonebot_plugin_larkhelp import panel

    fail_en = True

    async def flaky_render(
        user_id: str,
        _help_list: dict,
        **_kwargs: object,
    ) -> bytes:
        if fail_en and "--lang=en_us" in user_id:
            raise RuntimeError("transient error")
        return f"webp::{user_id}".encode()

    monkeypatch.setattr(panel, "render_help_panel", flaky_render)

    await cache.warm_up_cache()
    assert await cache.get_cache("en_us") is None
    assert await cache.get_cache("zh_hans") is not None
    assert await cache.get_cache("zh_tw") is not None

    fail_en = False
    await cache.scheduled_refresh_cache()
    assert await cache.get_cache("en_us") is not None


@pytest.mark.asyncio
async def test_render_help_panel_fast_hit_shares_across_themes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不同主题（default / wide / redpacket / simple）下 /help 均直接命中同一份语言磁盘缓存，不触发重绘"""
    import nonebot_plugin_larkhelp.cache as cache
    from nonebot_plugin_larkhelp import panel

    monkeypatch.setattr(cache, "cache_dir", tmp_path)
    monkeypatch.setattr(cache.config, "larkhelp_cache", True)
    await cache.set_cache("zh_hans", b"cached-webp-panel")

    async def should_not_run(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("命中磁盘缓存时不应收集指令文案或查询热门榜单")

    async def fake_get_lang(_user_id: str) -> str:
        return "zh_hans"

    monkeypatch.setattr(panel, "_get_lang", fake_get_lang)
    monkeypatch.setattr(panel, "_collect_rows", should_not_run)
    monkeypatch.setattr(panel, "_collect_texts", should_not_run)
    monkeypatch.setattr(panel, "_get_hot", should_not_run)

    fake_help_list = {"sign": _FakeHelp("sign", "game")}
    for theme in ("default", "simple", "redpacket", "wide"):
        result = await panel.render_help_panel(f"mlsid::--lang=zh_hans;--theme={theme}", fake_help_list)
        assert result == b"cached-webp-panel"
