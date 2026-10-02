"""`/chat review-all` 的行为测试

对所有会话执行记忆整理（Jev 判定并删除笔记）后重置它们的消息队列，属于管理操作，
仅超级用户可用。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

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


def _patch_lang(monkeypatch: pytest.MonkeyPatch) -> tuple[list[FinishCall], list[FinishCall]]:
    """替换 lang.finish / lang.send，记录本地化 key"""
    from nonebot_plugin_chat.matcher import chat

    finishes: list[FinishCall] = []
    sends: list[FinishCall] = []

    async def fake_finish(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> None:
        finishes.append((key, args))
        raise _FinishedError(key, args)

    async def fake_send(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> None:
        sends.append((key, args))

    monkeypatch.setattr(chat.lang, "finish", fake_finish)
    monkeypatch.setattr(chat.lang, "send", fake_send)
    return finishes, sends


@pytest.fixture
def superuser_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from nonebot_plugin_chat.matcher import chat

    spy = AsyncMock(return_value=False)
    monkeypatch.setattr(chat, "is_superuser", spy)
    return spy


@pytest.fixture
def review_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from nonebot_plugin_chat.matcher import chat

    spy = AsyncMock(return_value=(2, 3, 2))
    monkeypatch.setattr(chat, "review_and_reset_all_sessions", spy)
    return spy


async def test_review_all_requires_superuser(
    superuser_spy: AsyncMock,
    review_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非超级用户被拒绝，且不会启动整理"""
    finishes, sends = _patch_lang(monkeypatch)
    handler = _make_handler("review-all")

    with pytest.raises(_FinishedError):
        await handler.handle_review_all()

    assert finishes == [("command.review_all.no_permission", ())]
    assert sends == []
    review_spy.assert_not_awaited()


async def test_superuser_reviews_all_sessions(
    superuser_spy: AsyncMock,
    review_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超级用户会先收到「已开始」提示，随后收到处理结果"""
    superuser_spy.return_value = True
    finishes, sends = _patch_lang(monkeypatch)
    handler = _make_handler("review-all")

    with pytest.raises(_FinishedError):
        await handler.handle_review_all()

    assert sends == [("command.review_all.started", ())]
    assert finishes == [("command.review_all.success", (2, 3, 2))]
    review_spy.assert_awaited_once_with(source="ManualReviewAll")


async def test_dispatches_review_all_subcommand(
    superuser_spy: AsyncMock,
    review_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`chat review-all` 会分发到对应的处理方法"""
    superuser_spy.return_value = True
    finishes, _ = _patch_lang(monkeypatch)
    handler = _make_handler("review-all")

    with pytest.raises(_FinishedError):
        await handler.handle()

    assert finishes == [("command.review_all.success", (2, 3, 2))]


def _fake_session(session_id: str, review_result: int = 0, *, review_error: bool = False) -> Any:
    async def _reset(_session_id: str) -> None:
        return None

    return SimpleNamespace(
        session_id=session_id,
        processor=SimpleNamespace(openai_messages=SimpleNamespace(_reset_and_clear_db=AsyncMock(side_effect=_reset))),
        _review_result=review_result,
        _review_error=review_error,
    )


async def test_review_and_reset_all_sessions_counts() -> None:
    """每个活动会话都会被整理并重置，返回值汇总会话数 / 删除数 / 重置数"""
    from nonebot_plugin_chat.core import session as session_module

    sessions = {
        "qq_111": _fake_session("qq_111", review_result=2),
        "qq_222": _fake_session("qq_222", review_result=0),
    }

    async def fake_review(session: Any) -> int:
        if session._review_error:
            raise RuntimeError("jev down")
        return session._review_result

    fake_event_collector = SimpleNamespace(flush_pending=AsyncMock(return_value=[]))

    with (
        patch.object(session_module, "groups", sessions),
        patch("nonebot_plugin_chat.utils.note_manager.review_session_notes", AsyncMock(side_effect=fake_review)),
        patch("nonebot_plugin_chat.core.ego.event_collector.event_collector", fake_event_collector),
    ):
        reviewed, deleted, reset = await session_module.review_and_reset_all_sessions(source="Pytest")

    assert (reviewed, deleted, reset) == (2, 2, 2)
    for session in sessions.values():
        session.processor.openai_messages._reset_and_clear_db.assert_awaited_once()
    fake_event_collector.flush_pending.assert_awaited_once_with(min_pending=0)


async def test_review_and_reset_all_sessions_survives_failures() -> None:
    """单个会话整理或重置失败不影响其它会话"""
    from nonebot_plugin_chat.core import session as session_module

    broken = _fake_session("qq_111", review_error=True)
    broken.processor.openai_messages._reset_and_clear_db = AsyncMock(side_effect=RuntimeError("db down"))
    good = _fake_session("qq_222", review_result=1)
    sessions = {"qq_111": broken, "qq_222": good}

    async def fake_review(session: Any) -> int:
        if session._review_error:
            raise RuntimeError("jev down")
        return session._review_result

    with (
        patch.object(session_module, "groups", sessions),
        patch("nonebot_plugin_chat.utils.note_manager.review_session_notes", AsyncMock(side_effect=fake_review)),
        patch(
            "nonebot_plugin_chat.core.ego.event_collector.event_collector", SimpleNamespace(flush_pending=AsyncMock())
        ),
    ):
        reviewed, deleted, reset = await session_module.review_and_reset_all_sessions(source="Pytest")

    assert reviewed == 2
    assert deleted == 1
    assert reset == 1
    good.processor.openai_messages._reset_and_clear_db.assert_awaited_once_with("qq_222")
