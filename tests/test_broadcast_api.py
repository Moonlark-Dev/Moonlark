"""广播 HTTP 接口测试

覆盖：
1. 鉴权：API Token / 超管 Web 会话 / 无效凭据 / 非超管；
2. 参数校验：正文、按钮、目标群；
3. dry_run、幂等键、单并发与限流；
4. 后台发送任务与状态查询；
5. 广播记录状态（done/failed）与失败计数。
"""

import asyncio
from datetime import datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request, Response


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/broadcast",
            "headers": raw_headers,
            "client": ("127.0.0.1", 12345),
            "query_string": b"",
        },
    )


def _principal():
    from nonebot_plugin_broadcast.api import BroadcastPrincipal

    return BroadcastPrincipal(name="token:test", submitter="api:test", source="token")


def _plugin_data(buttons: list | None = None, disabled: list | None = None) -> dict:
    return {
        "counter": {"update_at": [2026, 11], "sent_count": 0},
        "latest": "",
        "disabled_groups": disabled or [],
        "buttons": buttons or [],
    }


def _fake_bot() -> MagicMock:
    bot = MagicMock()
    bot.self_id = "10000"
    bot.adapter.get_name.return_value = "OneBot V11"
    return bot


async def _drain_background_tasks() -> None:
    from nonebot_plugin_broadcast import api

    tasks = list(api._BACKGROUND_TASKS)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _finish_all_records() -> None:
    """把所有广播记录标为 done，避免测试之间互相影响（尤其是单并发判断）"""
    from nonebot_plugin_broadcast.models import BroadcastRecord
    from nonebot_plugin_orm import get_session
    from sqlalchemy import update

    async with get_session() as session:
        await session.execute(update(BroadcastRecord).values(status="done"))
        await session.commit()


@pytest.fixture(autouse=True)
async def _reset_broadcast_state():
    from nonebot_plugin_broadcast import api

    await _finish_all_records()
    api._rate_limiter = None
    yield
    await _drain_background_tasks()
    await _finish_all_records()
    api._rate_limiter = None


# ── 鉴权 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_token_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api.config, "broadcast_api_tokens", {"ci": "secret-token"})
    monkeypatch.setattr(api, "authenticate", AsyncMock(side_effect=AssertionError("不应查询 Web 会话")))

    principal = await api.get_broadcast_principal(_request({"Authorization": "Bearer secret-token"}))

    assert principal.name == "token:ci"
    assert principal.submitter == "api:ci"
    assert principal.source == "token"


@pytest.mark.asyncio
async def test_missing_authorization_returns_401() -> None:
    from nonebot_plugin_broadcast import api

    with pytest.raises(HTTPException) as error:
        await api.get_broadcast_principal(_request())

    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
async def test_empty_token_never_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置里留空的 token 不能变成「任何空凭据都能通过」"""
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api.config, "broadcast_api_tokens", {"ci": ""})
    monkeypatch.setattr(api, "authenticate", AsyncMock(side_effect=HTTPException(401)))

    with pytest.raises(HTTPException) as error:
        await api.get_broadcast_principal(_request({"Authorization": "Bearer whatever"}))

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_falls_back_to_superuser_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_larkuid.session import AuthContext
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api.config, "broadcast_api_tokens", {"ci": "secret-token"})
    monkeypatch.setattr(api.config, "superusers", ["10001"])
    monkeypatch.setattr(
        api,
        "authenticate",
        AsyncMock(return_value=AuthContext(session_id="session-id", user_id="10001", pending=False)),
    )

    principal = await api.get_broadcast_principal(_request({"Authorization": "Bearer session-id"}))

    assert principal.name == "user:10001"
    assert principal.submitter == "10001"
    assert principal.source == "session"


@pytest.mark.asyncio
async def test_session_user_must_be_superuser(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_larkuid.session import AuthContext
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api.config, "broadcast_api_tokens", {})
    monkeypatch.setattr(api.config, "superusers", [])
    monkeypatch.setattr(
        api,
        "authenticate",
        AsyncMock(return_value=AuthContext(session_id="session-id", user_id="20002", pending=False)),
    )

    with pytest.raises(HTTPException) as error:
        await api.get_broadcast_principal(_request({"Authorization": "Bearer session-id"}))

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_invalid_credential_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api.config, "broadcast_api_tokens", {"ci": "secret-token"})
    monkeypatch.setattr(api, "authenticate", AsyncMock(side_effect=HTTPException(401)))

    with pytest.raises(HTTPException) as error:
        await api.get_broadcast_principal(_request({"Authorization": "Bearer nope"}))

    assert error.value.status_code == 401


# ── 参数校验 ──────────────────────────────────────────────────────────


def test_normalize_rejects_empty_content() -> None:
    from nonebot_plugin_broadcast import api

    with pytest.raises(HTTPException) as error:
        api._normalize_request(api.BroadcastRequest(content="  \n "))

    assert error.value.status_code == 400


def test_normalize_rejects_long_content(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api.config, "broadcast_api_max_content_length", 4)

    with pytest.raises(HTTPException) as error:
        api._normalize_request(api.BroadcastRequest(content="12345"))

    assert error.value.status_code == 400


def test_normalize_buttons_and_targets() -> None:
    from nonebot_plugin_broadcast import api

    normalized = api._normalize_request(
        api.BroadcastRequest(
            content="  通知  ",
            buttons=[{"label": " 查看 ", "text": " /bc "}],
            targets=["123", 456, "123"],
        ),
    )

    assert normalized.content == "通知"
    assert normalized.buttons == [{"label": "查看", "text": "/bc"}]
    assert normalized.targets == ["123", "456"]


def test_normalize_rejects_invalid_buttons_and_targets() -> None:
    from nonebot_plugin_broadcast import api

    with pytest.raises(HTTPException) as error:
        api._normalize_request(api.BroadcastRequest(content="通知", buttons=[{"label": " ", "text": "/bc"}]))
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        api._normalize_request(api.BroadcastRequest(content="通知", targets=[]))
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        api._normalize_request(api.BroadcastRequest(content="通知", targets=["  "]))
    assert error.value.status_code == 400


# ── 接口行为 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dry_run_returns_targets_without_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data()))
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [_fake_bot()]}))
    create_record = AsyncMock()
    monkeypatch.setattr(api, "create_broadcast_record", create_record)

    response = Response()
    result = await api.create_broadcast(
        api.BroadcastRequest(content="维护通知", dry_run=True),
        _request(),
        response,
        _principal(),
    )

    assert response.status_code == 200
    assert result == {"dry_run": True, "total": 1, "targets": ["10001"]}
    create_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_broadcast_schedules_background_send(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api
    from nonebot_plugin_broadcast.push import BroadcastPushResult

    bot = _fake_bot()
    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data()))
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [bot]}))
    run = AsyncMock(return_value=BroadcastPushResult(broadcast_id=1, total=1, sent=1))
    monkeypatch.setattr(api, "run_broadcast", run)
    monkeypatch.setattr(api, "set_latest_broadcast_content", AsyncMock())

    result = await api.create_broadcast(
        api.BroadcastRequest(content="通知", targets=["10001"]),
        _request({"Idempotency-Key": "schedule-key"}),
        Response(),
        _principal(),
    )

    assert result["status"] == "queued"
    assert result["total"] == 1
    assert result["targets"] == ["10001"]
    assert result["idempotent"] is False
    await _drain_background_tasks()
    run.assert_awaited_once()
    assert run.await_args.args[1] == {"10001": [bot]}
    record = await api.get_broadcast_record(result["broadcast_id"])
    assert record is not None
    assert record.request_id == "schedule-key"


@pytest.mark.asyncio
async def test_idempotency_key_replays_without_sending_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api
    from nonebot_plugin_broadcast.push import BroadcastPushResult

    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data()))
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [_fake_bot()]}))
    run = AsyncMock(return_value=BroadcastPushResult(broadcast_id=1, total=1, sent=1))
    monkeypatch.setattr(api, "run_broadcast", run)
    monkeypatch.setattr(api, "set_latest_broadcast_content", AsyncMock())
    payload = api.BroadcastRequest(content="通知", targets=["10001"])

    first = await api.create_broadcast(payload, _request({"Idempotency-Key": "same-key"}), Response(), _principal())
    await _drain_background_tasks()
    second = await api.create_broadcast(payload, _request({"Idempotency-Key": "same-key"}), Response(), _principal())

    assert second["broadcast_id"] == first["broadcast_id"]
    assert second["idempotent"] is True
    assert run.await_count == 1


@pytest.mark.asyncio
async def test_idempotency_key_conflict_when_payload_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api
    from nonebot_plugin_broadcast.push import BroadcastPushResult

    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data()))
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [_fake_bot()]}))
    monkeypatch.setattr(
        api,
        "run_broadcast",
        AsyncMock(return_value=BroadcastPushResult(broadcast_id=1, total=1, sent=1)),
    )
    monkeypatch.setattr(api, "set_latest_broadcast_content", AsyncMock())

    await api.create_broadcast(
        api.BroadcastRequest(content="第一版通知", targets=["10001"]),
        _request({"Idempotency-Key": "conflict-key"}),
        Response(),
        _principal(),
    )
    await _drain_background_tasks()

    with pytest.raises(HTTPException) as error:
        await api.create_broadcast(
            api.BroadcastRequest(content="第二版通知", targets=["10001"]),
            _request({"Idempotency-Key": "conflict-key"}),
            Response(),
            _principal(),
        )

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_invalid_idempotency_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data()))
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [_fake_bot()]}))

    with pytest.raises(HTTPException) as error:
        await api.create_broadcast(
            api.BroadcastRequest(content="通知"),
            _request({"Idempotency-Key": "含 空格 的键"}),
            Response(),
            _principal(),
        )

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_unknown_target_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data()))
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [_fake_bot()]}))

    with pytest.raises(HTTPException) as error:
        await api.create_broadcast(
            api.BroadcastRequest(content="通知", targets=["10001", "99999"]),
            _request(),
            Response(),
            _principal(),
        )

    assert error.value.status_code == 400
    assert error.value.detail["targets"] == ["99999"]


@pytest.mark.asyncio
async def test_inflight_broadcast_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api

    await api.create_broadcast_record("进行中的广播", [], "api:test", total=1, status="queued")
    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data()))
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [_fake_bot()]}))

    with pytest.raises(HTTPException) as error:
        await api.create_broadcast(
            api.BroadcastRequest(content="新的广播"),
            _request(),
            Response(),
            _principal(),
        )

    assert error.value.status_code == 409
    assert error.value.headers == {"Retry-After": "30"}


@pytest.mark.asyncio
async def test_stale_running_record_is_cleaned_up() -> None:
    from nonebot_plugin_broadcast import api, push
    from nonebot_plugin_broadcast.models import BroadcastRecord
    from nonebot_plugin_orm import get_session
    from sqlalchemy import update

    broadcast_id = await api.create_broadcast_record("旧广播", [], "api:test", total=1, status="running")
    stale_at = datetime.now() - timedelta(seconds=push.INFLIGHT_STALE_SECONDS + 60)
    async with get_session() as session:
        await session.execute(
            update(BroadcastRecord).where(BroadcastRecord.id == broadcast_id).values(created_at=stale_at),
        )
        await session.commit()

    assert await push.find_inflight_broadcast() is None
    record = await push.get_broadcast_record(broadcast_id)
    assert record is not None
    assert record.status == "failed"


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api.config, "broadcast_api_rate_limit", 2)
    monkeypatch.setattr(api.config, "broadcast_api_rate_window", 60.0)
    api._rate_limiter = None
    principal = _principal()

    await api.enforce_broadcast_rate_limit(principal)
    await api.enforce_broadcast_rate_limit(principal)

    with pytest.raises(HTTPException) as error:
        await api.enforce_broadcast_rate_limit(principal)

    assert error.value.status_code == 429


# ── 查询 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_targets_endpoint_lists_available_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import api
    from nonebot_plugin_broadcast.groups import GroupSnapshot

    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data(disabled=["20002"])))
    monkeypatch.setattr(
        api,
        "list_group_snapshots",
        AsyncMock(
            return_value=[
                GroupSnapshot(
                    group_key="10001",
                    group_qq_number="10001",
                    group_openid="openid-1",
                    last_message_at=None,
                    bot_state_checked_at=None,
                    allow_proactive_msg=True,
                    recv_msg_setting=None,
                    member_role=None,
                    member_openid=None,
                    joined_at=None,
                ),
                GroupSnapshot(
                    group_key="20002",
                    group_qq_number="20002",
                    group_openid=None,
                    last_message_at=None,
                    bot_state_checked_at=None,
                    allow_proactive_msg=None,
                    recv_msg_setting=None,
                    member_role=None,
                    member_openid=None,
                    joined_at=None,
                ),
            ],
        ),
    )
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [_fake_bot()]}))

    result = await api.list_broadcast_targets(_principal())
    groups = {group["group_key"]: group for group in result["groups"]}

    assert groups["10001"]["available"] is True
    assert groups["10001"]["enabled"] is True
    assert groups["10001"]["target"] == "10001"
    assert groups["20002"]["enabled"] is False
    assert groups["20002"]["available"] is False


@pytest.mark.asyncio
async def test_status_endpoint_reports_events() -> None:
    from nonebot_plugin_broadcast import api
    from nonebot_plugin_broadcast.models import BroadcastPushEvent
    from nonebot_plugin_orm import get_session

    broadcast_id = await api.create_broadcast_record("通知", [], "api:test", total=1, status="done")
    async with get_session() as session:
        session.add(
            BroadcastPushEvent(
                broadcast_id=broadcast_id,
                group_key="10001",
                bot_id="10000",
                adapter="OneBot V11",
                mode="active",
                status="sent",
            ),
        )
        await session.commit()

    result = await api.get_broadcast_status(broadcast_id, principal=_principal())

    assert result["status"] == "done"
    assert result["total"] == 1
    assert result["submitter"] == "api:test"
    assert result["stats"]["sent"] == 1
    assert result["events"][0]["group_key"] == "10001"


@pytest.mark.asyncio
async def test_status_endpoint_returns_404() -> None:
    from nonebot_plugin_broadcast import api

    with pytest.raises(HTTPException) as error:
        await api.get_broadcast_status(999999999, principal=_principal())

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_http_routes_are_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """走真实 ASGI 路由：确认 /targets 不会被 /{broadcast_id} 抢先匹配，且请求体校验生效"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from nonebot import get_app

    from nonebot_plugin_broadcast import api

    monkeypatch.setattr(api, "get_plugin_data", AsyncMock(return_value=_plugin_data()))
    monkeypatch.setattr(api, "get_available_groups", AsyncMock(return_value={"10001": [_fake_bot()]}))
    monkeypatch.setattr(api, "list_group_snapshots", AsyncMock(return_value=[]))

    app = cast("FastAPI", get_app())
    app.dependency_overrides[api.get_broadcast_principal] = lambda: _principal()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            targets = await client.get("/api/broadcast/targets")
            assert targets.status_code == 200
            assert targets.json()["total"] == 0

            missing_body = await client.post("/api/broadcast", json={})
            assert missing_body.status_code == 422

            not_found = await client.get("/api/broadcast/999999999")
            assert not_found.status_code == 404
    finally:
        app.dependency_overrides.pop(api.get_broadcast_principal, None)


# ── 发送与记录状态 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_broadcast_counts_failures_and_marks_done(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import push
    from nonebot_plugin_broadcast.models import BroadcastRecord
    from nonebot_plugin_orm import get_session

    class _FailingMessage:
        def __init__(self) -> None:
            self.send = AsyncMock(side_effect=RuntimeError("boom"))

    monkeypatch.setattr(push, "SEND_INTERVAL_RANGE", (0, 0))
    monkeypatch.setattr(push, "render_broadcast_image", AsyncMock(return_value=None))
    monkeypatch.setattr(push, "build_broadcast_message", AsyncMock(return_value=_FailingMessage()))

    result = await push.push_broadcast_detailed({"10001": [_fake_bot()]}, "内容", [], submitter="api:test")

    assert (result.sent, result.pending, result.failed) == (0, 0, 1)
    async with get_session() as session:
        record = await session.get(BroadcastRecord, result.broadcast_id)
        assert record is not None
        assert record.status == "done"


@pytest.mark.asyncio
async def test_run_broadcast_marks_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    from nonebot_plugin_broadcast import push

    class _Message:
        def __init__(self) -> None:
            self.send = AsyncMock()

    monkeypatch.setattr(push, "SEND_INTERVAL_RANGE", (0, 0))
    monkeypatch.setattr(push, "render_broadcast_image", AsyncMock(return_value=None))
    monkeypatch.setattr(push, "build_broadcast_message", AsyncMock(return_value=_Message()))

    result = await push.push_broadcast_detailed({"10001": [_fake_bot()]}, "内容", [], submitter="api:test")

    assert (result.sent, result.pending, result.failed) == (1, 0, 0)
    stats = await push.get_broadcast_stats(result.broadcast_id)
    assert stats["sent"] == 1
