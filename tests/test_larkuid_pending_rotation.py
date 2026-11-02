"""登录激活轮换 session_id 后，/api/login/pending 仍能取回新会话 ID 的回归测试。

背景：``account verify`` 会删除待激活会话行、以新 session_id 重建（防 fixation）。
前端的长轮询仍拿着旧 ID，旧行删除后 ``authenticate`` 直接 401，前端把 401 当成
「验证超时，请重新登录」。修复后新行用 ``previous_session_id`` 指回旧 ID，
pending 在 401 时据此把新 ID 返回给前端。
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request

GET_SESSION = "nonebot_plugin_larkuid.session.get_session"

OLD_ID = "0" * 32
NEW_ID = "1" * 32


def _request(session_id: str, user_agent: str = "pytest-agent") -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/login/pending",
            "raw_path": b"/api/login/pending",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"authorization", f"Bearer {session_id}".encode()),
                (b"user-agent", user_agent.encode()),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )


async def _make_factory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    from nonebot_plugin_larkuid.models import SessionData

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SessionData.__table__.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _patch_session(factory: async_sessionmaker[AsyncSession]):
    return patch(GET_SESSION, side_effect=lambda **_: factory())


async def _add_rotated_session(
    factory: async_sessionmaker[AsyncSession],
    request: Request,
    *,
    expired: bool = False,
    identifier: str | None = None,
) -> None:
    from nonebot_plugin_larkuid.models import SessionData
    from nonebot_plugin_larkuid.session import get_identifier, utcnow

    async with factory() as session:
        session.add(
            SessionData(
                session_id=NEW_ID,
                user_id="user-1",
                identifier=identifier or get_identifier(request),
                activate_code=None,
                expiration_time=utcnow() - timedelta(seconds=1) if expired else utcnow() + timedelta(days=1),
                created_at=utcnow() - timedelta(minutes=1),
                last_active_at=utcnow() - timedelta(minutes=1),
                device="pytest",
                previous_session_id=OLD_ID,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_pending_returns_rotated_session_id() -> None:
    """旧 ID 已失效（401），但 pending 能通过 previous_session_id 取回新 ID。"""
    from nonebot_plugin_larkuid.session import InvalidSessionError, authenticate, get_rotated_session_id

    engine, factory = await _make_factory()
    request = _request(OLD_ID)
    await _add_rotated_session(factory, request)

    with _patch_session(factory):
        # 这正是修复前前端看到的 401：旧会话行已被 verify 删除
        with pytest.raises(InvalidSessionError):
            await authenticate(request)
        assert await get_rotated_session_id(request) == NEW_ID

    await engine.dispose()


@pytest.mark.asyncio
async def test_pending_endpoint_returns_activated_after_rotation() -> None:
    """pending 接口在轮换后返回 activated + 新 ID，而不是把 401 透传给前端。"""
    from nonebot_plugin_larkuid.web.login import _ as pending

    engine, factory = await _make_factory()
    request = _request(OLD_ID)
    await _add_rotated_session(factory, request)

    with _patch_session(factory):
        result = await pending(request, wait=0)

    assert result == {"activated": True, "session_id": NEW_ID}
    await engine.dispose()


@pytest.mark.asyncio
async def test_rotated_session_requires_matching_device() -> None:
    """设备标识不匹配时不能凭旧 ID 取回新会话（与正常鉴权的标识校验一致）。"""
    from nonebot_plugin_larkuid.session import get_rotated_session_id

    engine, factory = await _make_factory()
    request = _request(OLD_ID)
    await _add_rotated_session(factory, request, identifier="another-browser")

    with _patch_session(factory):
        assert await get_rotated_session_id(request) is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_rotated_session_expired() -> None:
    """新会话已过期时不再返回，避免把失效 ID 交给前端。"""
    from nonebot_plugin_larkuid.session import get_rotated_session_id

    engine, factory = await _make_factory()
    request = _request(OLD_ID)
    await _add_rotated_session(factory, request, expired=True)

    with _patch_session(factory):
        assert await get_rotated_session_id(request) is None

    await engine.dispose()
