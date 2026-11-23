"""``nonebot_plugin_larkuser`` 头像收集的回归测试。

QQ 官方 Bot 的 ``UserInfo.user_id`` 是 OpenID，而用户数据以主账号 ID（QQ 号）为主键。
此前的 recorder 直接用 OpenID 查 ``UserData``，只有 QQ 适配器的部署里用户全都有
OpenID → QQ 号的主账号映射，于是永远查不到这一行，昵称和头像都不会更新。
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def user_session():
    """只建立 UserData 表的内存数据库会话"""
    from nonebot_plugin_larkuser.models import UserData

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(UserData.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, factory
    await engine.dispose()


class _Avatar:
    def __init__(self, data: bytes = b"avatar-bytes", error: Exception | None = None):
        self.data = data
        self.error = error

    async def get_image(self) -> bytes:
        if self.error is not None:
            raise self.error
        return self.data


def _user_info(user_id: str, user_name: str = "", avatar: _Avatar | None = None) -> MagicMock:
    info = MagicMock()
    info.user_id = user_id
    info.user_name = user_name
    info.user_avatar = avatar
    return info


async def _add_user(session, user_id: str, nickname: str = "old", config: str = "{}") -> None:
    from nonebot_plugin_larkuser.models import UserData

    session.add(
        UserData(
            user_id=user_id,
            nickname=nickname,
            register_time=datetime(2026, 1, 1),
            config=config,
        )
    )
    await session.commit()


async def _get_user(factory, user_id: str):
    from nonebot_plugin_larkuser.models import UserData

    async with factory() as session:
        return await session.get(UserData, {"user_id": user_id})


@pytest.mark.asyncio
async def test_record_registered_user_uses_main_account(user_session, monkeypatch):
    """QQ OpenID 经主账号映射后，昵称与头像写进主账号那一行"""
    from nonebot_plugin_larkuser.matchers import recorder

    session, factory = user_session
    await _add_user(session, "1747433912", nickname="xxtg666")
    monkeypatch.setattr(recorder, "get_main_account", AsyncMock(return_value="1747433912"))
    update_avatar = AsyncMock()
    monkeypatch.setattr(recorder, "update_user_avatar", update_avatar)
    monkeypatch.setattr(recorder, "is_user_avatar_updated", AsyncMock(return_value=True))

    await recorder.record_registered_user(
        session,
        _user_info("B795A477BCCFA89F52B860374AAA32D3", "新昵称", _Avatar()),
    )

    update_avatar.assert_awaited_once_with("1747433912", b"avatar-bytes")
    row = await _get_user(factory, "1747433912")
    assert row is not None
    assert row.nickname == "新昵称"


@pytest.mark.asyncio
async def test_record_registered_user_without_mapping(user_session, monkeypatch):
    """没有主账号映射时（纯 QQ 用户），仍按原生 ID 正常更新"""
    from nonebot_plugin_larkuser.matchers import recorder

    session, factory = user_session
    await _add_user(session, "E0A9EE4013D97AA6E3C4DE6702E91CC9", nickname="k1s2y")
    monkeypatch.setattr(recorder, "get_main_account", AsyncMock(side_effect=lambda user_id: user_id))
    update_avatar = AsyncMock()
    monkeypatch.setattr(recorder, "update_user_avatar", update_avatar)
    monkeypatch.setattr(recorder, "is_user_avatar_updated", AsyncMock(return_value=True))

    await recorder.record_registered_user(
        session,
        _user_info("E0A9EE4013D97AA6E3C4DE6702E91CC9", "k1s2y", _Avatar()),
    )

    update_avatar.assert_awaited_once_with("E0A9EE4013D97AA6E3C4DE6702E91CC9", b"avatar-bytes")


@pytest.mark.asyncio
async def test_avatar_download_failure_does_not_block_nickname(user_session, monkeypatch):
    """头像图床故障时不影响昵称落库，也不让 matcher 抛异常"""
    from nonebot_plugin_larkuser.matchers import recorder

    session, factory = user_session
    await _add_user(session, "10001", nickname="old")
    monkeypatch.setattr(recorder, "get_main_account", AsyncMock(return_value="10001"))
    update_avatar = AsyncMock()
    monkeypatch.setattr(recorder, "update_user_avatar", update_avatar)

    await recorder.record_registered_user(
        session,
        _user_info("openid", "新昵称", _Avatar(error=RuntimeError("下载失败"))),
    )

    update_avatar.assert_not_awaited()
    row = await _get_user(factory, "10001")
    assert row is not None
    assert row.nickname == "新昵称"


@pytest.mark.asyncio
async def test_record_registered_user_respects_locked_nickname(user_session, monkeypatch):
    """锁定的昵称与头像不会被平台资料覆盖"""
    from nonebot_plugin_larkuser.matchers import recorder

    session, factory = user_session
    await _add_user(
        session,
        "10001",
        nickname="locked",
        config=json.dumps({"lock_nickname": True, "lock_avatar": True}),
    )
    monkeypatch.setattr(recorder, "get_main_account", AsyncMock(return_value="10001"))
    update_avatar = AsyncMock()
    monkeypatch.setattr(recorder, "update_user_avatar", update_avatar)
    monkeypatch.setattr(recorder, "is_user_avatar_updated", AsyncMock(return_value=True))

    await recorder.record_registered_user(session, _user_info("openid", "新昵称", _Avatar()))

    update_avatar.assert_not_awaited()
    row = await _get_user(factory, "10001")
    assert row is not None
    assert row.nickname == "locked"
