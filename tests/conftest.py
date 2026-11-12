import os

import pytest
import nonebot
from pytest_asyncio import is_async_test

# 导入适配器
from nonebot.adapters.console import Adapter as ConsoleAdapter
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# CI 通过环境变量把数据库指向 MySQL；本地未设置时才回落到内存 SQLite
os.environ.setdefault("SQLALCHEMY_DATABASE_URL", "sqlite+aiosqlite://")
os.environ["ALEMBIC_STARTUP_CHECK"] = "False"


def pytest_collection_modifyitems(items: list[pytest.Item]):
    pytest_asyncio_tests = (item for item in items if is_async_test(item))
    session_scope_marker = pytest.mark.asyncio(loop_scope="session")
    for async_test in pytest_asyncio_tests:
        async_test.add_marker(session_scope_marker, append=False)


async def _skip_htmlrender_startup(**_kwargs: object) -> None:
    """测试阶段跳过 HTMLRender 启动时的浏览器自检与预热。"""


async def _skip_htmlrender_install(*_args: object, **_kwargs: object) -> bool:
    """禁止在测试运行期触发 playwright install --with-deps 自动安装。"""
    return False


@pytest.fixture(scope="session", autouse=True)
async def after_nonebot_init(after_nonebot_init: None):
    # 加载适配器
    driver = nonebot.get_driver()
    driver.register_adapter(ConsoleAdapter)
    driver.register_adapter(OneBotV11Adapter)

    # 加载插件
    nonebot.load_from_toml("pyproject.toml")
    # nonebot.require("nonebot_plugin_chat")

    # nonebot_plugin_htmlrender 会在 ASGI startup 时自检并启动 Playwright 浏览器；
    # 若环境未预装浏览器则会执行 `playwright install --with-deps`，在 CI 上可能卡住长达 1 小时并最终失败。
    # 单元测试均 mock 渲染调用，这里跳过启动期浏览器初始化并禁用运行期自动安装。
    import nonebot_plugin_htmlrender
    from nonebot_plugin_htmlrender import browser as htmlrender_browser

    nonebot_plugin_htmlrender.init_browser = _skip_htmlrender_startup  # type: ignore[assignment]
    htmlrender_browser.install_browser = _skip_htmlrender_install
