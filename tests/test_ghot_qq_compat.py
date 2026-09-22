"""nonebot_plugin_ghot 的 QQ 官方适配器兼容性回归测试。

覆盖：
1. 两个处理器的事件参数可以同时接受 QQ 官方群消息与 OneBot V11 群消息
   （此前注解写死为 OneBot V11 的 `GroupMessageEvent`，QQ 群里会被依赖注入直接跳过）；
2. 同一物理群在 QQ 官方（group_openid）与 OneBot（群号）下的群键会按 GroupBind 合并；
3. `ghot history` 只查询传入的群键，不再读死群号；
4. 群内消息时间戳完全相同（时间轴长度为 0）时不会除零。
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _StubResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _StubSession:
    """记录查询语句、返回固定行的假 session"""

    def __init__(self, rows: list | None = None, scalar_result: object | None = None) -> None:
        self.rows = rows or []
        self.scalar_result = scalar_result
        self.statements: list = []
        self.scalar_statements: list = []

    async def scalars(self, statement: object) -> _StubResult:
        self.statements.append(statement)
        return _StubResult(self.rows)

    async def scalar(self, statement: object) -> object | None:
        self.scalar_statements.append(statement)
        return self.scalar_result


class _RecordingLang:
    async def text(self, key: str, _user_id: str, *_args: object) -> str:
        return key

    async def finish(self, key: str, _user_id: str, *_args: object) -> None:
        raise AssertionError(f"unexpected lang.finish({key})")


def _bound_parameters(statement: object, prefix: str = "group_id") -> set:
    """取出语句里指定前缀的绑定参数值，`IN` 展开后的列表会被摊平"""
    values: set = set()
    for name, value in statement.compile().params.items():
        if not name.startswith(prefix):
            continue
        values.update(value if isinstance(value, list) else [value])
    return values


def _event_fields(matcher: type) -> list:
    from nonebot.internal.params import EventParam

    return [
        (handler, field)
        for handler in matcher.handlers
        for field in handler.params
        if isinstance(field.field_info, EventParam)
    ]


def _qq_group_event():
    from nonebot.adapters.qq.event import GroupAtMessageCreateEvent

    return GroupAtMessageCreateEvent(
        id="msg-1",
        content="/ghot",
        timestamp="1700000000",
        group_id="group-id-1",
        group_openid="GROUP_OPENID_1",
        author={
            "id": "MEMBER_OPENID_1",
            "bot": False,
            "member_openid": "MEMBER_OPENID_1",
            "member_role": "member",
            "username": "tester",
        },
    )


def _ob11_group_event():
    from nonebot.adapters.onebot.v11.event import GroupMessageEvent, Sender

    return GroupMessageEvent(
        time=1700000000,
        self_id=123,
        post_type="message",
        message_type="group",
        sub_type="normal",
        message_id=1,
        group_id=701257458,
        user_id=10001,
        raw_message="/ghot",
        font=0,
        sender=Sender(user_id=10001, nickname="tester"),
        message=[{"type": "text", "data": {"text": "/ghot"}}],
    )


@pytest.mark.asyncio
async def test_handlers_accept_qq_group_event() -> None:
    """处理器的事件参数必须同时兼容 QQ 官方与 OneBot V11 的群消息事件"""
    import nonebot_plugin_ghot.__main__ as ghot

    checked = 0
    for _handler, field in _event_fields(ghot.ghot_cmd):
        for event in (_qq_group_event(), _ob11_group_event()):
            await field.field_info._check(event=event)  # ruff: ignore[private-member-access]
        checked += 1
    assert checked == 2


@pytest.mark.asyncio
async def test_resolve_group_keys_merges_bound_group() -> None:
    """群号与 group_openid 绑定后应合并为同一组的群键，群号键在前"""
    from nonebot_plugin_ghot.utils.group import resolve_group_keys

    bind = SimpleNamespace(group_qq_number="701257458", group_openid="GROUP_OPENID_1")

    by_qq_number = await resolve_group_keys(_StubSession(scalar_result=bind), "qq_701257458")
    assert by_qq_number == ["qq_701257458", "qq_GROUP_OPENID_1"]

    by_openid = await resolve_group_keys(_StubSession(scalar_result=bind), "qq_GROUP_OPENID_1")
    assert by_openid == ["qq_701257458", "qq_GROUP_OPENID_1"]


@pytest.mark.asyncio
async def test_resolve_group_keys_keeps_unbound_group() -> None:
    """未绑定的群与非 QQ 群键都只返回自身"""
    from nonebot_plugin_ghot.utils.group import resolve_group_keys

    unbound = _StubSession(scalar_result=None)
    assert await resolve_group_keys(unbound, "qq_1234567890") == ["qq_1234567890"]
    assert len(unbound.scalar_statements) == 1

    other_platform = _StubSession(scalar_result=None)
    assert await resolve_group_keys(other_platform, "telegram_-100123") == ["telegram_-100123"]
    assert other_platform.scalar_statements == []


@pytest.mark.asyncio
async def test_group_key_aliases_and_merge() -> None:
    """绑定表应生成 openid -> 群号 的别名，并把两条群键的消息合并"""
    from nonebot_plugin_ghot.utils.group import get_group_key_aliases, normalize_group_key
    from nonebot_plugin_ghot.utils.ranking import merge_group_messages

    session = _StubSession(
        rows=[
            SimpleNamespace(group_qq_number="701257458", group_openid="GROUP_OPENID_1"),
            SimpleNamespace(group_qq_number=None, group_openid="GROUP_OPENID_2"),
        ],
    )
    aliases = await get_group_key_aliases(session)
    assert aliases == {"qq_GROUP_OPENID_1": "qq_701257458"}
    assert normalize_group_key("qq_GROUP_OPENID_1", aliases) == "qq_701257458"

    first = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    second = datetime(2024, 1, 1, 12, 1, tzinfo=timezone.utc)
    merged = merge_group_messages(
        [
            SimpleNamespace(group_id="qq_GROUP_OPENID_1", timestamp=first),
            SimpleNamespace(group_id="qq_701257458", timestamp=second),
        ],
        aliases,
    )
    assert merged == {"qq_701257458": [first, second]}


@pytest.mark.asyncio
async def test_group_hot_score_queries_every_group_key() -> None:
    """热度统计应一次性查询同一物理群的全部群键"""
    from nonebot_plugin_ghot.utils.score import get_group_hot_score

    now = datetime.now()  # ruff: ignore[call-datetime-now-without-tzinfo]
    session = _StubSession(rows=[SimpleNamespace(timestamp=now)])
    scores = await get_group_hot_score(["qq_701257458", "qq_GROUP_OPENID_1"], session)
    assert len(scores) == 3

    assert _bound_parameters(session.statements[0]) == {"qq_701257458", "qq_GROUP_OPENID_1"}


@pytest.mark.asyncio
async def test_heat_chart_uses_requested_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """热力图必须使用传入的群键查询，不得再使用写死的群号"""
    from nonebot_plugin_ghot.utils import image

    monkeypatch.setattr(image, "lang", _RecordingLang())
    monkeypatch.setattr(image, "logger", MagicMock())

    rows = [
        SimpleNamespace(timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)),
        SimpleNamespace(timestamp=datetime(2024, 1, 1, 12, 10, tzinfo=timezone.utc)),
    ]
    session = _StubSession(rows=rows)
    raw = await image.render_heat_chart(session, "user-1", ["qq_701257458", "qq_GROUP_OPENID_1"])

    assert raw.startswith(b"\x89PNG")
    assert _bound_parameters(session.statements[0]) == {"qq_701257458", "qq_GROUP_OPENID_1"}


@pytest.mark.asyncio
async def test_heat_chart_handles_single_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有消息时间相同时时间轴长度为 0，渲染不应除零"""
    from nonebot_plugin_ghot.utils import image

    monkeypatch.setattr(image, "lang", _RecordingLang())
    monkeypatch.setattr(image, "logger", MagicMock())

    timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    session = _StubSession(rows=[SimpleNamespace(timestamp=timestamp)])
    raw = await image.render_heat_chart(session, "user-1", ["qq_701257458"])

    assert raw.startswith(b"\x89PNG")
