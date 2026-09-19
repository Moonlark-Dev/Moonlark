"""`/chat reset <会话ID>` 的行为测试

不带参数时保持原有语义：重置当前会话，任何用户可用。
带会话 ID 时属于管理操作：仅超级用户可用，且目标会话不存在时给出明确提示。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from nonebot_plugin_chat.matcher.chat import CommandHandler

FinishCall = tuple[str, tuple[Any, ...]]


class _FinishedError(Exception):
    """模拟 lang.finish 的终止语义（真实运行时由 matcher.finish 抛出 FinishedException）"""

    def __init__(self, key: str, args: tuple[Any, ...]) -> None:
        super().__init__(key)
        self.key = key
        self.args = args


def _make_handler(text: str) -> "CommandHandler":
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_chat.matcher.chat import CommandHandler

    return CommandHandler(MagicMock(), MagicMock(), MagicMock(), Message(text), MagicMock(), "10000", "10")


def _patch_finish(monkeypatch: pytest.MonkeyPatch) -> list[FinishCall]:
    """替换 lang.finish，记录本地化 key 并中断流程"""
    from nonebot_plugin_chat.matcher import chat

    calls: list[FinishCall] = []

    async def fake_finish(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> None:
        calls.append((key, args))
        raise _FinishedError(key, args)

    monkeypatch.setattr(chat.lang, "finish", fake_finish)
    return calls


@pytest.fixture
def reset_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from nonebot_plugin_chat.matcher import chat

    spy = AsyncMock(return_value=True)
    monkeypatch.setattr(chat, "reset_session", spy)
    return spy


@pytest.fixture
def superuser_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from nonebot_plugin_chat.matcher import chat

    spy = AsyncMock(return_value=False)
    monkeypatch.setattr(chat, "is_superuser", spy)
    return spy


async def test_reset_without_argument_resets_current_session(
    reset_spy: AsyncMock,
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不带参数：重置当前会话，且不进行超级用户校验"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("reset")

    with pytest.raises(_FinishedError):
        await handler.handle_reset()

    assert calls == [("command.reset.success", ())]
    reset_spy.assert_awaited_once_with("10000")
    superuser_spy.assert_not_awaited()


async def test_reset_without_argument_reports_not_found(
    reset_spy: AsyncMock,
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不带参数且没有活动会话时保持原有提示"""
    calls = _patch_finish(monkeypatch)
    reset_spy.return_value = False
    handler = _make_handler("reset")

    with pytest.raises(_FinishedError):
        await handler.handle_reset()

    assert calls == [("command.reset.not_found", ())]
    reset_spy.assert_awaited_once_with("10000")
    superuser_spy.assert_not_awaited()


async def test_reset_named_session_requires_superuser(
    reset_spy: AsyncMock,
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """指定会话 ID 时非超级用户被拒绝，且不会触碰目标会话"""
    calls = _patch_finish(monkeypatch)
    superuser_spy.return_value = False
    handler = _make_handler("reset 20000")

    with pytest.raises(_FinishedError):
        await handler.handle_reset()

    assert calls == [("command.reset.no_permission", ())]
    reset_spy.assert_not_awaited()


async def test_superuser_resets_named_session(
    reset_spy: AsyncMock,
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超级用户可以重置指定会话"""
    calls = _patch_finish(monkeypatch)
    superuser_spy.return_value = True
    handler = _make_handler("reset 20000")

    with pytest.raises(_FinishedError):
        await handler.handle_reset()

    assert calls == [("command.reset.session_success", ("20000",))]
    reset_spy.assert_awaited_once_with("20000")


async def test_superuser_named_session_not_found(
    reset_spy: AsyncMock,
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超级用户指定的会话不存在时给出包含该会话 ID 的提示"""
    calls = _patch_finish(monkeypatch)
    superuser_spy.return_value = True
    reset_spy.return_value = False
    handler = _make_handler("reset 20000")

    with pytest.raises(_FinishedError):
        await handler.handle_reset()

    assert calls == [("command.reset.session_not_found", ("20000",))]


async def test_blank_session_argument_falls_back_to_current_session(
    reset_spy: AsyncMock,
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """会话 ID 为空（多余空格）时回退到当前会话，避免误判为管理操作"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("reset  ")

    with pytest.raises(_FinishedError):
        await handler.handle_reset()

    assert calls == [("command.reset.success", ())]
    reset_spy.assert_awaited_once_with("10000")
    superuser_spy.assert_not_awaited()
