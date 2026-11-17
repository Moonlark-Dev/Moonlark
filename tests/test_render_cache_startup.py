"""Render 缓存创建时机的回归测试。

背景：缓存原本挂在 ``on_bot_connect`` 上创建。多账号进程里第一个 bot 连接时
``len(get_bots())`` 恰为 1，缓存会被生成；第二个 bot 连接时 ``len(get_bots())`` 变成 2，
于是先把第一个 bot 刚生成的缓存删掉、再跳过重建——进程里从此只有空缓存，所有
``cache=True`` 的渲染都退化成实时渲染。另外，挂在 bot 连接上也意味着第一条消息
可能赶在缓存创建之前。

现在改为在启动的 ready 阶段（所有插件的 ``on_startup`` 钩子执行完、bot 连接之前）
清空旧缓存并同步重建，预热直接阻塞启动。这里锁住四件事：钩子注册在 ready 阶段
（而不是 ``on_startup`` 或 bot 连接）、旧缓存会被清掉、预热按 模板 × 语言 × 主题
重建并在 ``prepare_cache`` 返回前完成、单个模板失败不会中断启动。
"""

from pathlib import Path
from typing import Any

import pytest


def _lifespan() -> Any:
    from nonebot import get_driver

    return get_driver()._lifespan


def test_cache_hook_is_registered_on_ready() -> None:
    """预热必须挂在 ready 阶段：它依赖的插件数据要在所有 on_startup 之后才就绪"""
    import nonebot_plugin_render.cache as cache

    lifespan = _lifespan()
    assert cache.prepare_cache in lifespan._ready_funcs
    assert cache.prepare_cache not in lifespan._startup_funcs


@pytest.fixture(autouse=True)
def fake_cache_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """把缓存目录、语言、主题和 creator 全部换成可控的假实现"""
    import nonebot_plugin_render.cache as cache

    rendered: list[str] = []

    async def creator(user_id: str) -> bytes:
        rendered.append(user_id)
        return f"image::{user_id}".encode()

    async def get_themes() -> dict[str, str]:
        return {"default": "base/default.html.jinja", "simple": "base/simple.html.jinja"}

    monkeypatch.setattr(cache, "cache_dir", tmp_path)
    monkeypatch.setattr(cache, "creator_functions", {"demo.html.jinja": creator})
    monkeypatch.setattr(cache, "get_languages", lambda: {"zh_hans": None, "en_us": None})
    monkeypatch.setattr(cache, "get_themes", get_themes)
    monkeypatch.setattr(cache.config, "render_cache", True)
    return rendered


@pytest.mark.asyncio
async def test_prepare_cache_clears_stale_files_and_warms_up_synchronously(
    fake_cache_environment: list[str], tmp_path: Path
) -> None:
    """启动阶段先清掉上次运行的缓存，再同步重建——返回时缓存必须已经就绪"""
    import nonebot_plugin_render.cache as cache

    stale = tmp_path / "stale-cache"
    stale.write_bytes(b"old")
    subdirectory = tmp_path / "nested"
    subdirectory.mkdir()

    await cache.prepare_cache()

    assert not stale.exists(), "上次运行的缓存必须被清掉"
    assert subdirectory.is_dir(), "清理缓存不能误删目录"
    assert await cache.get_cache("demo.html.jinja", "zh_hans", "default") is not None
    assert len(fake_cache_environment) == 4, "预热必须在 prepare_cache 返回前完成，不能留给后台任务"
    assert len([path for path in tmp_path.iterdir() if path.is_file()]) == 4


@pytest.mark.asyncio
async def test_prepare_cache_respects_disabled_config(
    fake_cache_environment: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RENDER_CACHE=false 时仍然清理旧缓存，但不做预热"""
    import nonebot_plugin_render.cache as cache

    monkeypatch.setattr(cache.config, "render_cache", False)
    stale = tmp_path / "stale-cache"
    stale.write_bytes(b"old")

    await cache.prepare_cache()

    assert not stale.exists()
    assert not fake_cache_environment, "关闭缓存时不应调用 creator"
    assert not any(path.is_file() for path in tmp_path.iterdir()), "关闭缓存时不应写入缓存"


@pytest.mark.asyncio
async def test_warm_up_cache_rebuilds_every_combination(tmp_path: Path) -> None:
    """启动预热按 模板 × 语言 × 主题 逐个重建缓存"""
    import nonebot_plugin_render.cache as cache

    await cache.warm_up_cache()

    languages = ("zh_hans", "en_us")
    themes = ("default", "simple")
    for lang in languages:
        for theme in themes:
            assert await cache.get_cache("demo.html.jinja", lang, theme) is not None
    assert len(list(tmp_path.iterdir())) == len(languages) * len(themes)


@pytest.mark.asyncio
async def test_warm_up_cache_skips_empty_and_failed_creators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """单个组合渲染失败或返回空数据时跳过，既不影响其他缓存也不向外抛异常"""
    import nonebot_plugin_render.cache as cache

    rendered: list[str] = []

    async def flaky_creator(user_id: str) -> bytes:
        rendered.append(user_id)
        if "--theme=simple" in user_id:
            raise RuntimeError("渲染炸了")
        if "--lang=en_us" in user_id:
            return b""
        return b"image"

    monkeypatch.setattr(cache, "creator_functions", {"demo.html.jinja": flaky_creator})

    await cache.warm_up_cache()

    assert await cache.get_cache("demo.html.jinja", "zh_hans", "default") == b"image"
    assert await cache.get_cache("demo.html.jinja", "zh_hans", "simple") is None
    assert await cache.get_cache("demo.html.jinja", "en_us", "default") is None
    assert len(list(tmp_path.iterdir())) == 1
    assert all("--ignore-cache=y" in user_id for user_id in rendered)
