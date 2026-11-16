"""Chat 的模型 Provider：``/chat model`` 指令与全局 / 分会话设置读写"""

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


class _RecordingMatcher:
    """记录发给 matcher 的文本，并用异常模拟 finish 终止处理器"""

    def __init__(self) -> None:
        self.finished: list[str] = []

    async def finish(self, text: str = "") -> None:
        self.finished.append(text)
        raise _FinishedError(text, ())


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
def provider_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """把 /chat model 依赖的读写函数替换成内存实现"""
    from nonebot_plugin_chat.matcher import chat

    state: dict[str, Any] = {"global": "openai", "sessions": {}, "session_sets": []}

    async def fake_global() -> str:
        return state["global"]

    async def fake_set_global(provider: str) -> None:
        state["global"] = provider

    async def fake_reset_global() -> None:
        state["global"] = chat.DEFAULT_PROVIDER

    async def fake_get_session(session_id: str) -> str | None:
        return state["sessions"].get(session_id)

    async def fake_get(session_id: str | None = None) -> str:
        if session_id:
            provider = state["sessions"].get(session_id)
            if provider is not None:
                return provider
        return state["global"]

    async def fake_set_session(session_id: str, provider: str) -> None:
        state["session_sets"].append((session_id, provider))
        state["sessions"][session_id] = provider

    async def fake_clear_session(session_id: str) -> bool:
        return state["sessions"].pop(session_id, None) is not None

    async def fake_list_sessions() -> dict[str, str]:
        return dict(sorted(state["sessions"].items()))

    async def fake_text(key: str, _user_id: str, *args: Any, **_kwargs: Any) -> str:
        return key + (("|" + "|".join(str(arg) for arg in args)) if args else "")

    monkeypatch.setattr(chat, "get_global_model_provider", fake_global)
    monkeypatch.setattr(chat, "set_global_model_provider", fake_set_global)
    monkeypatch.setattr(chat, "reset_global_model_provider", fake_reset_global)
    monkeypatch.setattr(chat, "get_session_model_provider", fake_get_session)
    monkeypatch.setattr(chat, "get_model_provider", fake_get)
    monkeypatch.setattr(chat, "set_session_model_provider", fake_set_session)
    monkeypatch.setattr(chat, "clear_session_model_provider", fake_clear_session)
    monkeypatch.setattr(chat, "list_session_model_providers", fake_list_sessions)
    monkeypatch.setattr(chat.lang, "text", fake_text)
    return state


@pytest.fixture
def superuser_spy(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from nonebot_plugin_chat.matcher import chat

    spy = AsyncMock(return_value=True)
    monkeypatch.setattr(chat, "is_superuser", spy)
    return spy


async def test_model_requires_superuser(
    provider_state: dict[str, Any],
    superuser_spy: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非超级用户不能查看或修改 Provider"""
    calls = _patch_finish(monkeypatch)
    superuser_spy.return_value = False
    handler = _make_handler("model gemini")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.no_permission", ())]
    assert provider_state["global"] == "openai"


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_without_argument_shows_rules_and_settings() -> None:
    """不带参数时展示命令规则、全局默认、当前会话与所有分会话设置"""
    handler = _make_handler("model")
    matcher = _RecordingMatcher()
    handler.matcher = matcher

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    text = matcher.finished[0]
    assert "command.model.rules" in text
    assert "command.model.global|openai" in text
    # 当前会话没有单独设置，应显示跟随全局与全局默认值
    assert "command.model.current|10000|openai|command.model.source.global" in text
    # 没有分会话设置时展示「暂无」提示
    assert "command.model.no_sessions" in text


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_without_argument_marks_current_session_custom(provider_state: dict[str, Any]) -> None:
    """当前会话单独设置过时，概览里应标注「单独设置」并使用该 Provider"""
    provider_state["global"] = "openai"
    provider_state["sessions"] = {"10000": "gemini"}
    handler = _make_handler("model")
    matcher = _RecordingMatcher()
    handler.matcher = matcher

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert "command.model.current|10000|gemini|command.model.source.session" in matcher.finished[0]


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_without_argument_lists_session_settings(provider_state: dict[str, Any]) -> None:
    """概览列出所有单独设置的会话与 Provider"""
    provider_state["global"] = "openai"
    provider_state["sessions"] = {"qq_200": "gemini"}
    handler = _make_handler("model")
    matcher = _RecordingMatcher()
    handler.matcher = matcher

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    text = matcher.finished[0]
    assert "command.model.sessions" in text
    assert "command.model.session_line|qq_200|gemini" in text
    assert "command.model.no_sessions" not in text


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_sets_global_default(monkeypatch: pytest.MonkeyPatch, provider_state: dict[str, Any]) -> None:
    """不带会话 ID 时切换全局默认 Provider"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("model Gemini")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert provider_state["global"] == "gemini"
    assert calls == [("command.model.changed", ("gemini",))]


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_sets_session_provider(monkeypatch: pytest.MonkeyPatch, provider_state: dict[str, Any]) -> None:
    """带会话 ID 时为该会话单独设置 Provider"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("model gemini qq_200")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert provider_state["sessions"] == {"qq_200": "gemini"}
    assert provider_state["global"] == "openai"
    assert calls == [("command.model.session_changed", ("qq_200", "gemini"))]


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_session_unchanged(monkeypatch: pytest.MonkeyPatch, provider_state: dict[str, Any]) -> None:
    """会话已经使用该 Provider 时给出 unchanged 提示"""
    calls = _patch_finish(monkeypatch)
    provider_state["sessions"] = {"qq_200": "gemini"}
    handler = _make_handler("model gemini qq_200")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.session_unchanged", ("qq_200", "gemini"))]
    assert provider_state["session_sets"] == []


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_global_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """全局默认已经是该 Provider 时给出 unchanged 提示"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("model openai")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.unchanged", ("openai",))]


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_default_resets_session(monkeypatch: pytest.MonkeyPatch, provider_state: dict[str, Any]) -> None:
    """``default`` + 会话 ID 清除该会话设置，重新跟随全局"""
    calls = _patch_finish(monkeypatch)
    provider_state["global"] = "gemini"
    provider_state["sessions"] = {"qq_200": "openai"}
    handler = _make_handler("model default qq_200")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert provider_state["sessions"] == {}
    assert calls == [("command.model.session_reset", ("qq_200", "gemini"))]


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_default_on_session_without_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """对没有设置的会话使用 ``default`` 时提示已经在跟随全局"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("model default qq_200")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.session_default_unchanged", ("qq_200",))]


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_default_resets_global(monkeypatch: pytest.MonkeyPatch, provider_state: dict[str, Any]) -> None:
    """不带会话 ID 的 ``default`` 把全局默认恢复成 openai"""
    calls = _patch_finish(monkeypatch)
    provider_state["global"] = "gemini"
    handler = _make_handler("model default")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert provider_state["global"] == "openai"
    assert calls == [("command.model.reset", ("openai",))]


@pytest.mark.usefixtures("provider_state", "superuser_spy")
async def test_model_invalid_provider(monkeypatch: pytest.MonkeyPatch, provider_state: dict[str, Any]) -> None:
    """非法 Provider 名给出可选值提示，且不改动设置"""
    calls = _patch_finish(monkeypatch)
    handler = _make_handler("model claude")

    with pytest.raises(_FinishedError):
        await handler.handle_model()

    assert calls == [("command.model.invalid", ("claude", "openai|gemini|default"))]
    assert provider_state["global"] == "openai"


async def test_session_label_uses_cached_session_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """活跃会话的缓存数据能拿到名称时，展示「会话 ID（名称）」"""
    from nonebot_plugin_chat.matcher import chat

    class _PrivateSession:
        nickname = "小明"

        @staticmethod
        def get_session_type() -> str:
            return "private"

    class _GroupSession:
        @staticmethod
        def get_session_type() -> str:
            return "group"

        @staticmethod
        async def get_session_name() -> str:
            return "测试群"

    monkeypatch.setattr(chat, "groups", {"qq_1": _PrivateSession(), "qq_2": _GroupSession()})

    assert await chat.format_session_label("qq_1") == "qq_1（小明）"
    assert await chat.format_session_label("qq_2") == "qq_2（测试群）"
    # 非活跃会话没有缓存数据，只显示 ID
    assert await chat.format_session_label("qq_3") == "qq_3"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("openai", "openai"), ("Gemini", "gemini"), (" GEMINI ", "gemini"), ("claude", None), ("", None)],
)
def test_normalize_provider(value: str, expected: Any) -> None:
    """Provider 名规范化：大小写与空白不敏感，非法值返回 None"""
    from nonebot_plugin_chat.utils.provider import normalize_provider

    assert normalize_provider(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("default", True), (" DEFAULT ", True), (":default:", True), ("openai", False)],
)
def test_is_default_provider(value: str, expected: bool) -> None:
    """``default`` 是恢复默认的保留值（也接受 ``:default:``），大小写与空白不敏感"""
    from nonebot_plugin_chat.utils.provider import is_default_provider

    assert is_default_provider(value) is expected


class _FakeScalars:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class _FakeSession:
    def __init__(self, setting: Any = None, rows: list[Any] | None = None) -> None:
        self.setting = setting
        self.rows = rows or []
        self.merged: list[Any] = []
        self.deleted: list[Any] = []
        self.executed: list[Any] = []
        self.commits = 0

    async def get(self, _model: Any, _pk: Any) -> Any:
        return self.setting

    async def merge(self, obj: Any) -> None:
        self.merged.append(obj)

    async def delete(self, obj: Any) -> None:
        self.deleted.append(obj)

    async def execute(self, statement: Any) -> None:
        self.executed.append(statement)

    async def scalars(self, _statement: Any) -> _FakeScalars:
        return _FakeScalars(self.rows)

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "openai"), ("gemini", "gemini"), ("openai", "openai"), ("claude", "openai")],
)
async def test_get_global_model_provider(monkeypatch: pytest.MonkeyPatch, value: str | None, expected: str) -> None:
    """读取全局默认：未设置或值非法时回落到 openai"""
    from nonebot_plugin_chat.models import ChatGlobalSetting
    from nonebot_plugin_chat.utils import provider

    setting = ChatGlobalSetting(key="model_provider", value=value) if value is not None else None
    fake = _FakeSession(setting)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    assert await provider.get_global_model_provider() == expected


async def test_set_global_model_provider_creates_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有记录时写入一条新的全局设置"""
    from nonebot_plugin_chat.utils import provider

    fake = _FakeSession(None)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    await provider.set_global_model_provider("gemini")

    assert [(obj.key, obj.value) for obj in fake.merged] == [("model_provider", "gemini")]
    assert fake.commits == 1


async def test_set_global_model_provider_updates_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """已有全局记录时就地更新"""
    from nonebot_plugin_chat.models import ChatGlobalSetting
    from nonebot_plugin_chat.utils import provider

    setting = ChatGlobalSetting(key="model_provider", value="openai")
    fake = _FakeSession(setting)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    await provider.set_global_model_provider("gemini")

    assert setting.value == "gemini"
    assert fake.commits == 1


async def test_reset_global_model_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """恢复全局默认时删除全局设置记录"""
    from nonebot_plugin_chat.utils import provider

    fake = _FakeSession(None)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    await provider.reset_global_model_provider()

    assert len(fake.executed) == 1
    assert fake.commits == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("gemini", "gemini"), ("openai", "openai"), ("claude", None)],
)
async def test_get_session_model_provider(
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
    expected: str | None,
) -> None:
    """读取分会话设置：未设置或值非法时返回 None（跟随全局）"""
    from nonebot_plugin_chat.models import ChatSessionSetting
    from nonebot_plugin_chat.utils import provider

    setting = ChatSessionSetting(session_id="qq_1", key="model_provider", value=value) if value is not None else None
    fake = _FakeSession(setting)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    assert await provider.get_session_model_provider("qq_1") == expected


async def test_get_session_model_provider_ignores_empty_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """空会话 ID 直接返回 None，不查数据库"""
    from nonebot_plugin_chat.utils import provider

    fake = _FakeSession(None)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    assert await provider.get_session_model_provider("") is None
    assert fake.setting is None


async def test_set_session_model_provider_creates_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """没有记录时为会话写入一条新设置"""
    from nonebot_plugin_chat.utils import provider

    fake = _FakeSession(None)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    await provider.set_session_model_provider("qq_1", "gemini")

    assert [(obj.session_id, obj.key, obj.value) for obj in fake.merged] == [("qq_1", "model_provider", "gemini")]
    assert fake.commits == 1


async def test_set_session_model_provider_updates_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """已有会话记录时就地更新"""
    from nonebot_plugin_chat.models import ChatSessionSetting
    from nonebot_plugin_chat.utils import provider

    setting = ChatSessionSetting(session_id="qq_1", key="model_provider", value="openai")
    fake = _FakeSession(setting)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    await provider.set_session_model_provider("qq_1", "gemini")

    assert setting.value == "gemini"
    assert fake.commits == 1


async def test_clear_session_model_provider_deletes_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """清除会话设置时删除记录并返回 True"""
    from nonebot_plugin_chat.models import ChatSessionSetting
    from nonebot_plugin_chat.utils import provider

    setting = ChatSessionSetting(session_id="qq_1", key="model_provider", value="gemini")
    fake = _FakeSession(setting)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    assert await provider.clear_session_model_provider("qq_1") is True
    assert fake.deleted == [setting]
    assert fake.commits == 1


async def test_clear_session_model_provider_without_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """会话没有设置时清除返回 False，不提交空事务"""
    from nonebot_plugin_chat.utils import provider

    fake = _FakeSession(None)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    assert await provider.clear_session_model_provider("qq_1") is False
    assert fake.deleted == []
    assert fake.commits == 0


async def test_list_session_model_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """列出分会话设置：按会话 ID 排序并忽略非法值"""
    from nonebot_plugin_chat.models import ChatSessionSetting
    from nonebot_plugin_chat.utils import provider

    rows = [
        ChatSessionSetting(session_id="qq_2", key="model_provider", value="openai"),
        ChatSessionSetting(session_id="qq_1", key="model_provider", value="gemini"),
        ChatSessionSetting(session_id="qq_3", key="model_provider", value="claude"),
    ]
    fake = _FakeSession(None, rows)
    monkeypatch.setattr(provider, "get_session", lambda: fake)

    assert await provider.list_session_model_providers() == {"qq_1": "gemini", "qq_2": "openai"}


async def test_get_model_provider_prefers_session_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """带会话 ID 时优先使用该会话的设置"""
    from nonebot_plugin_chat.utils import provider

    async def fake_get_session(session_id: str) -> str | None:
        return "gemini" if session_id == "qq_1" else None

    async def fake_global() -> str:
        return "openai"

    monkeypatch.setattr(provider, "get_session_model_provider", fake_get_session)
    monkeypatch.setattr(provider, "get_global_model_provider", fake_global)

    assert await provider.get_model_provider("qq_1") == "gemini"


async def test_get_model_provider_falls_back_to_global(monkeypatch: pytest.MonkeyPatch) -> None:
    """会话没有单独设置时回落到全局默认"""
    from nonebot_plugin_chat.utils import provider

    async def fake_get_session(_session_id: str) -> str | None:
        return None

    async def fake_global() -> str:
        return "gemini"

    monkeypatch.setattr(provider, "get_session_model_provider", fake_get_session)
    monkeypatch.setattr(provider, "get_global_model_provider", fake_global)

    assert await provider.get_model_provider("qq_1") == "gemini"


@pytest.mark.parametrize(("value", "expected"), [("gemini", 300), ("openai", 600)])
async def test_sliding_window_idle_seconds(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    expected: int,
) -> None:
    """Gemini 模式下 block 选择（滑动窗口）的等待时长缩短到 5 分钟"""
    from nonebot_plugin_chat.utils import provider

    seen: list[str | None] = []

    async def fake_get(session_id: str | None = None) -> str:
        seen.append(session_id)
        return value

    monkeypatch.setattr(provider, "get_model_provider", fake_get)

    assert await provider.get_sliding_window_idle_seconds("qq_1") == expected
    assert seen == ["qq_1"]
