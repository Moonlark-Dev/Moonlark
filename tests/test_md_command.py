from unittest.mock import AsyncMock

import pytest
from nonebot.exception import FinishedException


@pytest.fixture(autouse=True)
def patched_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 md 插件的 LangHelper.text，避免依赖数据库读取语言文本

    注意：插件导入必须在函数/fixture 内部进行（collection 阶段 nonebot 插件尚未加载）。
    """
    from nonebot_plugin_md.__main__ import lang

    async def fake_text(key: str, _user_id: str, *_args: object, **_kwargs: object) -> str:
        return f"text::{key}"

    monkeypatch.setattr(lang, "text", fake_text)


def _raising_finish() -> AsyncMock:
    """模拟真实 LangHelper.finish：调用后抛出 FinishedException 以终止处理器流程"""
    return AsyncMock(side_effect=FinishedException())


def test_md_command_registered_with_larkutils_superuser_permission() -> None:
    """/md 指令应存在，且使用 larkutils 的 is_superuser 校验超管（先映射主账号再比对 SUPERUSERS）"""
    from nonebot.permission import Permission
    from nonebot_plugin_larkutils.superuser import is_superuser
    from nonebot_plugin_md.__main__ import md_cmd

    assert md_cmd
    permission = md_cmd.permission
    assert isinstance(permission, Permission)
    # 权限检查器应包含 larkutils 的 is_superuser
    assert any(checker.call is is_superuser for checker in permission.checkers)


@pytest.mark.asyncio
async def test_process_md_non_qq_platform_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 QQ 官方机器人（如 OneBot V11）使用 /md 应提示 unsupported_platform 且不发送消息"""
    from unittest.mock import MagicMock

    from nonebot_plugin_md.__main__ import _process_md, lang

    finish = _raising_finish()
    monkeypatch.setattr(lang, "finish", finish)

    matcher = MagicMock()
    # MagicMock 不是 nonebot.adapters.qq.Bot 的实例，应走到 unsupported_platform 分支
    with pytest.raises(FinishedException):
        await _process_md(matcher, MagicMock(), MagicMock(), "10", "## 标题")

    assert finish.call_args.args == ("unsupported_platform", "10")
    matcher.finish.assert_not_called()


@pytest.mark.asyncio
async def test_process_md_empty_content_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    """空参数应提示 empty，且不发送任何 markdown 消息"""
    from unittest.mock import MagicMock

    from nonebot_plugin_md.__main__ import _process_md, lang

    class FakeQQBot:
        """模拟 QQ 官方机器人 Bot 实例"""

    finish = _raising_finish()
    monkeypatch.setattr(lang, "finish", finish)
    # 将模块内的 QQBot 指向假类，使 isinstance 检查通过
    monkeypatch.setattr("nonebot_plugin_md.__main__.QQBot", FakeQQBot)
    # 使用假的 UniMessage 观察 style/send 调用
    sent: list[tuple] = []

    class FakeUniMessage:
        def style(self, content: str, style: str) -> "FakeUniMessage":
            self.content = content
            self.style = style
            return self

        async def send(self, target: object = None, bot: object = None) -> None:
            sent.append((self.content, self.style, target, bot))

    monkeypatch.setattr("nonebot_plugin_md.__main__.UniMessage", FakeUniMessage)

    event = MagicMock()
    matcher = MagicMock()
    with pytest.raises(FinishedException):
        await _process_md(matcher, FakeQQBot(), event, "10", "   ")

    assert finish.call_args.args == ("empty", "10")
    assert sent == []
    matcher.finish.assert_not_called()


@pytest.mark.asyncio
async def test_process_md_qq_sends_raw_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方机器人下应将参数中的 Markdown 原样以 markdown 样式发送到当前会话并结束处理器"""
    from unittest.mock import MagicMock

    from nonebot_plugin_md.__main__ import _process_md, lang

    class FakeQQBot:
        """模拟 QQ 官方机器人 Bot 实例"""

    finish = AsyncMock()
    monkeypatch.setattr(lang, "finish", finish)
    monkeypatch.setattr("nonebot_plugin_md.__main__.QQBot", FakeQQBot)

    sent: list[tuple] = []

    class FakeUniMessage:
        def style(self, content: str, style: str) -> "FakeUniMessage":
            self.content = content
            self.style = style
            return self

        async def send(self, target: object = None, bot: object = None) -> None:
            sent.append((self.content, self.style, target, bot))

    monkeypatch.setattr("nonebot_plugin_md.__main__.UniMessage", FakeUniMessage)

    matcher = MagicMock()
    matcher.finish = AsyncMock()
    event = MagicMock()
    bot = FakeQQBot()
    content = "## 标题\n\n**加粗** [链接](https://example.com) `代码`"
    await _process_md(matcher, bot, event, "10", content)

    # Markdown 原样发送，不转义不加工
    assert sent == [(content, "markdown", event, bot)]
    finish.assert_not_called()
    matcher.finish.assert_awaited_once()
