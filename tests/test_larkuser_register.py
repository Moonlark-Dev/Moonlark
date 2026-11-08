"""静默自动注册的回归测试。

Moonlark 删除了独立的 ``register`` 指令：需要注册的指令会在执行前通过
:func:`ensure_registered` 静默完成注册，且不再询问昵称。

这里覆盖：

- 平台能提供昵称时直接使用，拿不到时回退为 ``用户-{user_id}``；
- 已注册用户重复触发注册时不会覆盖昵称与注册时间；
- :func:`ensure_registered` 只在未注册时写入数据。
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


def _user_info(user_name):
    info = MagicMock()
    info.user_name = user_name
    return info


async def _load(factory, user_id: str):
    from nonebot_plugin_larkuser.models import UserData

    async with factory() as session:
        return await session.get(UserData, {"user_id": user_id})


# ---------------------------------------------------------- register_user --


@pytest.mark.asyncio
async def test_register_user_uses_platform_nickname(user_session):
    """平台能提供昵称时直接使用，不再询问用户"""
    from nonebot_plugin_larkuser.utils import register

    session, factory = user_session

    assert await register.register_user(session, "10001", _user_info("小明")) == "小明"

    row = await _load(factory, "10001")
    assert row is not None
    assert row.nickname == "小明"
    assert row.register_time is not None
    assert json.loads(row.config)["lock_nickname"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("user_name", [None, "", "   "])
async def test_register_user_falls_back_to_default_nickname(user_name, user_session):
    """平台昵称为空时回退为 用户-{user_id}，不写入 NULL / 空白昵称"""
    from nonebot_plugin_larkuser.utils import register

    session, factory = user_session

    assert await register.register_user(session, "10001", _user_info(user_name)) == "用户-10001"

    row = await _load(factory, "10001")
    assert row is not None
    assert row.nickname == "用户-10001"


@pytest.mark.asyncio
async def test_register_user_without_user_info_uses_default(user_session):
    """拿不到平台用户信息时同样使用兜底昵称，而不是等待用户输入"""
    from nonebot_plugin_larkuser.utils import register

    session, factory = user_session

    assert await register.register_user(session, "10002") == "用户-10002"
    assert (await _load(factory, "10002")).nickname == "用户-10002"


@pytest.mark.asyncio
async def test_register_user_is_idempotent(user_session):
    """已注册用户重复触发注册时不应覆盖昵称与注册时间"""
    from nonebot_plugin_larkuser.models import UserData
    from nonebot_plugin_larkuser.utils import register

    session, factory = user_session
    original_time = datetime(2020, 1, 1)
    async with factory() as seed_session:
        seed_session.add(UserData(user_id="10003", nickname="老昵称", register_time=original_time))
        await seed_session.commit()

    assert await register.register_user(session, "10003", _user_info("新昵称")) == "老昵称"

    row = await _load(factory, "10003")
    assert row.nickname == "老昵称"
    assert row.register_time == original_time


# ------------------------------------------------------- ensure_registered --


@pytest.mark.asyncio
async def test_ensure_registered_writes_for_unregistered_user(monkeypatch, user_session):
    """未注册用户会被静默写入 UserData，且返回 True 表示确实注册了"""
    from nonebot_plugin_larkuser.utils import register

    _, factory = user_session
    monkeypatch.setattr(register, "is_user_registered", AsyncMock(return_value=False))
    monkeypatch.setattr(register, "get_session", lambda: factory())

    assert await register.ensure_registered("10004", _user_info("小明")) is True
    assert (await _load(factory, "10004")).nickname == "小明"


@pytest.mark.asyncio
async def test_ensure_registered_skips_registered_user(monkeypatch, user_session):
    """已注册用户不会再次写库，也不产生任何提示"""
    from nonebot_plugin_larkuser.utils import register

    _, factory = user_session
    monkeypatch.setattr(register, "is_user_registered", AsyncMock(return_value=True))

    def _unexpected_session():
        raise AssertionError("已注册用户不应再打开会话写库")

    monkeypatch.setattr(register, "get_session", _unexpected_session)

    assert await register.ensure_registered("10005", _user_info("小明")) is False


# ------------------------------------------------------------ check_access --


@pytest.mark.asyncio
async def test_check_access_registers_unregistered_user_silently(monkeypatch):
    """未注册用户使用需要注册的指令时静默注册，不发送任何提示"""
    from nonebot_plugin_larkuser.utils import matcher as matcher_module

    user = MagicMock()
    user.is_down = AsyncMock(return_value=False)
    user.get_register_time = MagicMock(return_value=None)
    monkeypatch.setattr(matcher_module, "get_user", AsyncMock(return_value=user))
    ensure_registered = AsyncMock(return_value=True)
    monkeypatch.setattr(matcher_module, "ensure_registered", ensure_registered)
    send_down_prompt = AsyncMock()
    monkeypatch.setattr(matcher_module, "send_down_prompt", send_down_prompt)
    user_info = _user_info("小明")

    await matcher_module.check_access(user_id="10001", user_info=user_info)

    ensure_registered.assert_awaited_once_with("10001", user_info)
    send_down_prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_access_keeps_registered_user_untouched(monkeypatch):
    """已注册用户不会被重复注册"""
    from datetime import datetime

    from nonebot_plugin_larkuser.utils import matcher as matcher_module

    user = MagicMock()
    user.is_down = AsyncMock(return_value=False)
    user.get_register_time = MagicMock(return_value=datetime.now())
    monkeypatch.setattr(matcher_module, "get_user", AsyncMock(return_value=user))
    ensure_registered = AsyncMock()
    monkeypatch.setattr(matcher_module, "ensure_registered", ensure_registered)

    await matcher_module.check_access(user_id="10002", user_info=None)

    ensure_registered.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_access_blocks_downed_user(monkeypatch):
    """倒地用户会收到提示并终止当前响应器"""
    from datetime import timedelta

    from nonebot.exception import FinishedException
    from nonebot_plugin_larkuser.utils import matcher as matcher_module

    user = MagicMock()
    user.is_down = AsyncMock(return_value=True)
    user.get_down_remaining = MagicMock(return_value=timedelta(minutes=10))
    monkeypatch.setattr(matcher_module, "get_user", AsyncMock(return_value=user))
    send_down_prompt = AsyncMock()
    monkeypatch.setattr(matcher_module, "send_down_prompt", send_down_prompt)
    matcher = MagicMock()
    matcher.finish = AsyncMock(side_effect=FinishedException)

    with pytest.raises(FinishedException):
        await matcher_module.check_access(matcher=matcher, user_id="10003", user_info=None)

    send_down_prompt.assert_awaited_once_with("10003", timedelta(minutes=10))
    matcher.finish.assert_awaited_once()
