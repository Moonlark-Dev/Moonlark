"""HTMLRender 在测试环境下的启动与自动安装保护回归测试。

背景：``nonebot_plugin_htmlrender`` 在 ASGI startup 时会自检并启动 Playwright 浏览器；
当 CI 环境未预装对应浏览器二进制时，会自动执行 ``playwright install --with-deps``，
在 Ubuntu runner 上卡住子进程/apt 锁长达 1 小时并最终因缺少浏览器可执行文件导致全部测试 setup 报错。
"""

from unittest.mock import AsyncMock

import pytest


async def test_htmlrender_startup_skips_browser_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """ASGI startup 钩子不应在测试启动阶段拉起 Playwright 浏览器。"""
    import nonebot_plugin_htmlrender
    from nonebot_plugin_htmlrender import browser as htmlrender_browser

    start_browser = AsyncMock()
    monkeypatch.setattr(htmlrender_browser, "start_browser", start_browser)

    await nonebot_plugin_htmlrender.init()

    start_browser.assert_not_awaited()


async def test_htmlrender_runtime_auto_install_is_disabled() -> None:
    """测试运行期禁止触发 playwright install --with-deps 自动安装。"""
    from nonebot_plugin_htmlrender import browser as htmlrender_browser

    assert await htmlrender_browser.install_browser() is False
