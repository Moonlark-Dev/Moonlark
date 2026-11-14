"""Chat 插件的全局模型 Provider：``/chat model`` 指令与 Provider 设置读写"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FinishedError(Exception):
    """模拟 lang.finish 的终止语义"""

    def __init__(self, key: str, args: tuple[Any, ...]) -> None:
        super().__init__(key)
        self.key = key
        self.args = args


def _make_handler(text: str) -> Any:
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_chat.matcher.chat import CommandHandler

    return CommandHandler(MagicMock(), MagicMock(), MagicMock(), Message(text), MagicMock(), "10000", "10")


def _patch_finish(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    from nonebot_plugin_chat.matcher import chat

    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_finish(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> None:
        calls.append((key, args))
        raise _FinishedError(key, args)

    monkeypatch.setattr(chat.lang, "finish", fake_finish)
    return calls


@pytest.fixture
def provider_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """把 /chat model 依赖的读写函数替换成内存实现"""
    from nonebot_plugin_chat.matcher import chat

    state = {"provider": "openai"}

    async def fake_get() -> str:
        return state["provider"]

    async def fake_set(provider: str) -> None:
        state["provider"] = provider

    monkeypatch.setattr(chat, "get_model_provider", fake_get)
    monkeypatch.setattr(chat, "set_model_provider", fake_set)
    return state


@pytest.fixture
def superuser_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from nonebot_plugin_chat.matcher import chat

    spy = AsyncMock(return_value=True)
    monkeypatch.setattr(chat, "is_superuser", spy)
    return spy


async def test_model_requires_superuser(
    provider_state: dict[str, str],
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非超级用户不能切换 Provider"""
    calls = _patch_finish(monkeypatch)
    superuser_spy.return_value = False
    handler = _make_handler("model gemini")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.no_permission", ())]
    assert provider_state["provider"] == "openai"


async def test_model_without_argument_shows_current_provider(
    provider_state: dict[str, str],
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不带参数时展示当前 Provider"""
    calls = _patch_finish(monkeypatch)
    provider_state["provider"] = "gemini"
    handler = _make_handler("model")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.current", ("gemini",))]


async def test_model_switches_provider(
    provider_state: dict[str, str],
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超级用户可以切换全局 Provider"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("model Gemini")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.changed", ("gemini",))]
    assert provider_state["provider"] == "gemini"


async def test_model_unchanged(
    provider_state: dict[str, str],
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重复设置当前 Provider 时给出 ``unchanged`` 提示"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("model openai")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.unchanged", ("openai",))]


async def test_model_invalid_provider(
    provider_state: dict[str, str],
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非法 Provider 名给出可选值提示，且不改动设置"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("model claude")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.invalid", ("claude", "openai|gemini"))]
    assert provider_state["provider"] == "openai"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("openai", "openai"), ("Gemini", "gemini"), (" GEMINI ", "gemini"), ("claude", None), ("", None)],
)
def test_normalize_provider(value: str, expected: Any) -> None:
    """Provider 名规范化：大小写与空白不敏感，非法值返回 None"""
    from nonebot_plugin_chat.utils.provider import normalize_provider

    assert normalize_provider(value) == expected


class _FakeSession:
    def __init__(self, setting: Any = None) -> None:
        self.setting = setting
        self.merged: list[Any] = []
        self.commits = 0

    async def get(self, _model: Any, _pk: Any) -> Any:
        return self.setting

    async def merge(self, obj: Any) -> None:
        self.merged.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "openai"), ("gemini", "gemini"), ("openai", "openai"), ("claude", "openai")],
)
async def test_get_model_provider(monkeypatch: pytest.MonkeyPatch, value: str | None, expected: str) -> None:
    """读取 Provider：未设置或值非法时回落到 openai"""
    from nonebot_plugin_chat.models import ChatGlobalSetting
    from nonebot_plugin_chat.utils import provider

    setting = ChatGlobalSetting(key="model_provider", value=value) if value is not None else None
    fake = _FakeSession(setting)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    assert await provider.get_model_provider() == expected


async def test_set_model_provider_creates_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有记录时写入一条新设置"""
    from nonebot_plugin_chat.utils import provider

    fake = _FakeSession(None)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    await provider.set_model_provider("gemini")

    assert [(obj.key, obj.value) for obj in fake.merged] == [("model_provider", "gemini")]
    assert fake.commits == 1


async def test_set_model_provider_updates_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """已有记录时就地更新"""
    from nonebot_plugin_chat.models import ChatGlobalSetting
    from nonebot_plugin_chat.utils import provider

    setting = ChatGlobalSetting(key="model_provider", value="openai")
    fake = _FakeSession(setting)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    await provider.set_model_provider("gemini")

    assert setting.value == "gemini"
    assert fake.commits == 1


@pytest.mark.parametrize(("value", "expected"), [("gemini", 300), ("openai", 600)])
async def test_sliding_window_idle_seconds(monkeypatch: pytest.MonkeyPatch, value: str, expected: int) -> None:
    """Gemini 模式下 block 选择（滑动窗口）的等待时长缩短到 5 分钟"""
    from nonebot_plugin_chat.utils import provider

    async def fake_get() -> str:
        return value

    monkeypatch.setattr(provider, "get_model_provider", fake_get)

    assert await provider.get_sliding_window_idle_seconds() == expected
