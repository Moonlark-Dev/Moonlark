import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _clean_markdown_cache():
    """每个用例前清空全局指令列表缓存，避免用例间互相污染"""
    import nonebot_plugin_command_helper.__main__ as main

    main.commands_markdown = ""
    yield
    main.commands_markdown = ""


@pytest.mark.asyncio
async def test_generate_commands_markdown_contains_commands() -> None:
    """生成的 markdown 应包含普通指令与 superuser 指令"""
    from nonebot_plugin_command_helper.__main__ import generate_commands_markdown

    async def fake_text(key: str, _user_id: str, *args, **_kwargs) -> str:
        # 模拟 larkhelp 的 markdown 模板渲染
        templates = {
            "markdown.title": "# Moonlark 指令列表\n\n",
            "markdown.command": "## `{}`: {}\n\n{}\n",
            "markdown.usage": "- `{}`\n",
            "markdown.superuser_warning": "> 此指令仅 Moonlark 管理员可用。",
        }
        if key == "markdown.title":
            return templates[key]
        if key == "markdown.command":
            return templates[key].format(*args)
        if key == "markdown.usage":
            return templates[key].format(*args)
        if key == "markdown.superuser_warning":
            return templates[key]
        return ""

    normal_cmd = {
        "name": "jrrp",
        "description": "今日人品",
        "details": "查询今天的人品值",
        "usages": ["/jrrp (获取今天的人品值)"],
    }
    superuser_cmd = {
        "name": "model",
        "description": "模型管理",
        "details": "管理 OpenAI 模型配置",
        "usages": ["/model (查看模型配置信息)"],
    }

    with (
        patch(
            "nonebot_plugin_command_helper.__main__.setup_help_list",
            new=AsyncMock(),
        ),
        patch(
            "nonebot_plugin_command_helper.__main__.load_languages",
            new=AsyncMock(),
        ),
        patch(
            "nonebot_plugin_command_helper.__main__.get_templates",
            new=AsyncMock(return_value=[{"commands": [normal_cmd]}]),
        ),
        patch(
            "nonebot_plugin_command_helper.__main__.get_menu_templates",
            new=AsyncMock(return_value=[{"id": "superuser", "commands": [superuser_cmd]}]),
        ),
        patch(
            "nonebot_plugin_command_helper.__main__.larkhelp_lang.text",
            new=fake_text,
        ),
    ):
        markdown = await generate_commands_markdown()

    assert "Moonlark 指令列表" in markdown
    assert "## `jrrp`: 今日人品" in markdown
    assert "查询今天的人品值" in markdown
    assert "- `/jrrp (获取今天的人品值)`" in markdown
    assert "## `model`: 模型管理" in markdown
    assert "此指令仅 Moonlark 管理员可用。" in markdown


@pytest.mark.asyncio
async def test_get_commands_markdown_caches_result() -> None:
    """get_commands_markdown 应缓存生成结果，不重复生成"""
    from nonebot_plugin_command_helper.__main__ import get_commands_markdown

    with patch(
        "nonebot_plugin_command_helper.__main__.generate_commands_markdown",
        new=AsyncMock(return_value="# cached markdown"),
    ) as mocked_generate:
        first = await get_commands_markdown()
        second = await get_commands_markdown()

    assert first == "# cached markdown"
    assert second == "# cached markdown"
    mocked_generate.assert_awaited_once()


class _FakeFetcher:
    """模拟 MessageFetcher，fetch_last_message 返回预设结果"""

    def __init__(self, result: str):
        self.result = result

    async def fetch_last_message(self) -> str:
        return self.result


@pytest.mark.asyncio
async def test_handle_command_with_query() -> None:
    """/command 带查询参数：发送 thinking → 调用 LLM → 回复结果"""
    from nonebot_plugin_command_helper.__main__ import handle_command

    fake_lang = AsyncMock()
    fake_lang.send.return_value = None
    fake_lang.finish.side_effect = RuntimeError("finish 应中断 handler")

    with (
        patch("nonebot_plugin_command_helper.__main__.lang", fake_lang),
        patch(
            "nonebot_plugin_command_helper.__main__.get_commands_markdown",
            new=AsyncMock(return_value="# Moonlark 指令列表\n\n## `jrrp`: 今日人品\n"),
        ),
        patch(
            "nonebot_plugin_command_helper.__main__.MessageFetcher.create",
            new=AsyncMock(return_value=_FakeFetcher("用法：/jrrp 获取今天的人品值")),
        ) as mocked_create,
    ):
        with pytest.raises(RuntimeError):
            await handle_command(("jrrp", "怎么用"), user_id="user-1")

    fake_lang.send.assert_awaited_once_with("thinking", "user-1")
    fake_lang.finish.assert_awaited_once()
    args = fake_lang.finish.await_args
    assert args.args[0] == "result"
    assert args.args[1] == "user-1"
    assert args.args[2] == "用法：/jrrp 获取今天的人品值"
    # LLM 调用：system 含指令列表，user 含查询内容
    mocked_create.assert_awaited_once()
    create_args = mocked_create.await_args.args[0]
    assert create_args[0]["role"] == "system"
    assert "Moonlark 指令列表" in create_args[0]["content"]
    assert create_args[1]["role"] == "user"
    assert create_args[1]["content"] == "jrrp 怎么用"
    assert mocked_create.await_args.kwargs["identify"] == "Command Helper"


@pytest.mark.asyncio
async def test_handle_command_without_query() -> None:
    """/command 无参数：提示用法"""
    from nonebot_plugin_command_helper.__main__ import handle_command

    fake_lang = AsyncMock()
    fake_lang.finish.side_effect = RuntimeError("finish 应中断 handler")

    with patch("nonebot_plugin_command_helper.__main__.lang", fake_lang):
        with pytest.raises(RuntimeError):
            await handle_command((), user_id="user-1")

    fake_lang.finish.assert_awaited_once_with("usage", "user-1")


@pytest.mark.asyncio
async def test_handle_command_llm_error() -> None:
    """LLM 调用失败时提示 llm_error"""
    from nonebot_plugin_command_helper.__main__ import handle_command

    fake_lang = AsyncMock()
    fake_lang.send.return_value = None
    fake_lang.finish.side_effect = RuntimeError("finish 应中断 handler")

    with (
        patch("nonebot_plugin_command_helper.__main__.lang", fake_lang),
        patch(
            "nonebot_plugin_command_helper.__main__.get_commands_markdown",
            new=AsyncMock(return_value="# Moonlark 指令列表\n"),
        ),
        patch(
            "nonebot_plugin_command_helper.__main__.MessageFetcher.create",
            new=AsyncMock(side_effect=Exception("LLM 超时")),
        ),
    ):
        with pytest.raises(RuntimeError):
            await handle_command(("jrrp",), user_id="user-1")

    fake_lang.finish.assert_awaited_once_with("llm_error", "user-1")


@pytest.mark.asyncio
async def test_handle_command_commands_error() -> None:
    """指令列表生成失败时提示 commands_error"""
    from nonebot_plugin_command_helper.__main__ import handle_command

    fake_lang = AsyncMock()
    fake_lang.send.return_value = None
    fake_lang.finish.side_effect = RuntimeError("finish 应中断 handler")

    with (
        patch("nonebot_plugin_command_helper.__main__.lang", fake_lang),
        patch(
            "nonebot_plugin_command_helper.__main__.get_commands_markdown",
            new=AsyncMock(side_effect=Exception("collect 失败")),
        ),
    ):
        with pytest.raises(RuntimeError):
            await handle_command(("jrrp",), user_id="user-1")

    fake_lang.finish.assert_awaited_once_with("commands_error", "user-1")
