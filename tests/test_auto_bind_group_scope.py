"""auto bind 的群作用域测试。

auto bind 依靠「同一用户经两个适配器发出的相同消息」完成绑定，因此只应在
OneBot 11 群号与 QQ 官方 group_openid 已经双向绑定（GroupBind 两列都有值）的群里生效。

覆盖：
1. 未绑定、只有单边绑定的群不会进入匹配缓存，也不会触发绑定；
2. 已双向绑定的群按 OneBot 11 群号配对，仍然可以完成绑定；
3. 两个不同群里的相同消息不会互相配对；
4. 私聊保持原有行为，且不会查询群绑定；
5. 群绑定查询失败时只跳过本次自动绑定，不向事件预处理链抛异常。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _v11_bot():
    from nonebot.adapters.onebot.v11 import Bot as V11Bot

    return MagicMock(spec=V11Bot)


def _qq_bot():
    from nonebot.adapters.qq import Bot as QQBot

    return MagicMock(spec=QQBot)


def _v11_group_event(group_id: int = 70001, user_id: str = "10001", text: str = "你好"):
    return SimpleNamespace(
        group_id=group_id,
        get_plaintext=lambda: text,
        get_user_id=lambda: user_id,
    )


def _v11_private_event(user_id: str = "10001", text: str = "你好"):
    return SimpleNamespace(
        get_plaintext=lambda: text,
        get_user_id=lambda: user_id,
    )


def _qq_group_event(group_openid: str = "openid-1", user_id: str = "member-openid", text: str = "你好"):
    return SimpleNamespace(
        group_openid=group_openid,
        get_plaintext=lambda: text,
        get_user_id=lambda: user_id,
    )


def _qq_private_event(user_id: str = "c2c-openid", text: str = "你好"):
    return SimpleNamespace(
        get_plaintext=lambda: text,
        get_user_id=lambda: user_id,
    )


def _bind(group_qq_number: str | None, group_openid: str | None) -> SimpleNamespace:
    return SimpleNamespace(group_qq_number=group_qq_number, group_openid=group_openid)


@pytest.fixture(autouse=True)
def _reset_auto_bind_cache(monkeypatch: pytest.MonkeyPatch):
    """每个用例前清空匹配缓存，并把头像与绑定副作用换成桩。"""
    from nonebot_plugin_auto_bind import main

    main._recent_messages.clear()
    monkeypatch.setattr(main, "get_user_info", AsyncMock(return_value=SimpleNamespace(user_avatar=object())))
    monkeypatch.setattr(main, "_get_avatar_hash", AsyncMock(return_value="avatar-hash"))
    monkeypatch.setattr(main, "_try_bind", AsyncMock())
    yield
    main._recent_messages.clear()


@pytest.fixture
def bound_groups(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], SimpleNamespace]:
    """用内存字典模拟 GroupBind 查询，键为 ("ob11", 群号) / ("qq", group_openid)。"""
    from nonebot_plugin_auto_bind import main

    records: dict[tuple[str, str], SimpleNamespace] = {}

    async def _by_ob11_group(group_qq_number: str):
        return records.get(("ob11", group_qq_number))

    async def _by_qqbot_group(group_openid: str):
        return records.get(("qq", group_openid))

    monkeypatch.setattr(main, "get_group_bind_by_ob11_group", _by_ob11_group)
    monkeypatch.setattr(main, "get_group_bind_by_qqbot_group", _by_qqbot_group)
    return records


@pytest.mark.asyncio
async def test_unbound_group_is_skipped(bound_groups: dict) -> None:
    """两个适配器都没绑定过的群：不缓存、不绑定。"""
    from nonebot_plugin_auto_bind import main

    await main._(_v11_bot(), _v11_group_event())
    await main._(_qq_bot(), _qq_group_event())

    assert main._recent_messages == []
    main._try_bind.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_sided_binding_is_skipped(bound_groups: dict) -> None:
    """只完成单边绑定（等待另一端输入验证码）的群同样关闭 auto bind。"""
    from nonebot_plugin_auto_bind import main

    bound_groups[("ob11", "70001")] = _bind("70001", None)
    bound_groups[("qq", "openid-1")] = _bind(None, "openid-1")

    await main._(_v11_bot(), _v11_group_event())
    await main._(_qq_bot(), _qq_group_event())

    assert main._recent_messages == []
    main._try_bind.assert_not_awaited()


@pytest.mark.asyncio
async def test_bound_group_still_binds(bound_groups: dict) -> None:
    """双向绑定的共享群里，同一条消息仍然可以完成 auto bind。"""
    from nonebot_plugin_auto_bind import main

    bind = _bind("70001", "openid-1")
    bound_groups[("ob11", "70001")] = bind
    bound_groups[("qq", "openid-1")] = bind

    await main._(_v11_bot(), _v11_group_event(user_id="10001"))
    assert len(main._recent_messages) == 1

    await main._(_qq_bot(), _qq_group_event(user_id="member-openid"))

    main._try_bind.assert_awaited_once_with("member-openid", "10001")
    assert main._recent_messages == []


@pytest.mark.asyncio
async def test_messages_from_different_groups_do_not_match(bound_groups: dict) -> None:
    """两个不同共享群里的相同消息不能互相配对。"""
    from nonebot_plugin_auto_bind import main

    bound_groups[("ob11", "70001")] = _bind("70001", "openid-a")
    bound_groups[("qq", "openid-b")] = _bind("70002", "openid-b")

    await main._(_v11_bot(), _v11_group_event(group_id=70001))
    await main._(_qq_bot(), _qq_group_event(group_openid="openid-b"))

    assert len(main._recent_messages) == 2
    main._try_bind.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_chat_keeps_original_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    """私聊不查群绑定，仍按原有逻辑配对。"""
    from nonebot_plugin_auto_bind import main

    ob11_lookup = AsyncMock()
    qq_lookup = AsyncMock()
    monkeypatch.setattr(main, "get_group_bind_by_ob11_group", ob11_lookup)
    monkeypatch.setattr(main, "get_group_bind_by_qqbot_group", qq_lookup)

    await main._(_v11_bot(), _v11_private_event(user_id="10001"))
    await main._(_qq_bot(), _qq_private_event(user_id="c2c-openid"))

    main._try_bind.assert_awaited_once_with("c2c-openid", "10001")
    ob11_lookup.assert_not_awaited()
    qq_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_binding_lookup_failure_only_skips_auto_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    """查询群绑定失败时不能抛出异常，否则会阻断整条消息的处理。"""
    from nonebot_plugin_auto_bind import main

    monkeypatch.setattr(
        main,
        "get_group_bind_by_ob11_group",
        AsyncMock(side_effect=RuntimeError("database is down")),
    )

    await main._(_v11_bot(), _v11_group_event())

    assert main._recent_messages == []
    main._try_bind.assert_not_awaited()


@pytest.mark.asyncio
async def test_bots_group_bind_helpers_query_by_each_side(monkeypatch: pytest.MonkeyPatch) -> None:
    """nonebot_plugin_bots 暴露的两个查询分别按群号 / group_openid 命中同一条绑定记录。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from nonebot_plugin_bots import (
        __main__ as bots_main,
        get_group_bind_by_ob11_group,
        get_group_bind_by_qqbot_group,
    )
    from nonebot_plugin_bots.models import GroupBind

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(GroupBind.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(GroupBind(group_qq_number="70001", group_openid="openid-1"))
        await session.commit()

    monkeypatch.setattr(bots_main, "get_session", factory)

    by_ob11 = await get_group_bind_by_ob11_group("70001")
    by_qq = await get_group_bind_by_qqbot_group("openid-1")

    assert by_ob11 is not None and by_ob11.group_openid == "openid-1"
    assert by_qq is not None and by_qq.group_qq_number == "70001"
    assert await get_group_bind_by_ob11_group("70002") is None
    assert await get_group_bind_by_qqbot_group("openid-2") is None
    await engine.dispose()
