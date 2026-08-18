import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    """真实 sqlite 内存库，建好 GroupMessage 表"""
    from nonebot_plugin_message_summary.models import GroupMessage

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(GroupMessage.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _add_messages(session_factory: async_sessionmaker[AsyncSession], group_id: str, count: int) -> None:
    from nonebot_plugin_message_summary.models import GroupMessage

    async with session_factory() as session:
        for i in range(count):
            session.add(
                GroupMessage(
                    message=f"msg-{i}",
                    sender_nickname="sender",
                    user_id="user-1",
                    group_id=group_id,
                ),
            )
        await session.commit()


@pytest.mark.asyncio
async def test_get_offset_message_returns_nth_latest(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """/wdym N：指令消息记为 0，第 N 条为目标；超出记录数时返回 None"""
    from nonebot_plugin_wdym.matcher import _get_offset_message

    await _add_messages(session_factory, "g", 5)
    async with session_factory() as session:
        assert (await _get_offset_message(session, "g", 1)).message == "msg-4"
        assert (await _get_offset_message(session, "g", 3)).message == "msg-2"
        assert (await _get_offset_message(session, "g", 5)).message == "msg-0"
        assert await _get_offset_message(session, "g", 6) is None


@pytest.mark.asyncio
async def test_get_offset_message_scoped_to_group(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """只统计同一群内的消息"""
    from nonebot_plugin_wdym.matcher import _get_offset_message

    await _add_messages(session_factory, "g-a", 3)
    await _add_messages(session_factory, "g-b", 1)
    async with session_factory() as session:
        assert (await _get_offset_message(session, "g-a", 1)).message == "msg-2"
        assert (await _get_offset_message(session, "g-b", 1)).message == "msg-0"
        assert await _get_offset_message(session, "g-b", 2) is None


@pytest.mark.asyncio
async def test_get_offset_replied_raw_zero_uses_command_message(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """偏移量为 0 时目标即指令消息本身，且不依赖收集器记录"""
    from nonebot.adapters.onebot.v11 import Message

    from fake import fake_group_message_event_v11
    from nonebot_plugin_wdym.matcher import get_offset_replied_raw

    event = fake_group_message_event_v11(message=Message("/wdym 0"))
    state: dict = {}
    async with session_factory() as session:
        text = await get_offset_replied_raw(state, event, session, "user-1", "g", 0)
    assert text == "/wdym 0"
    assert state.get("replied_id") is None
    assert state.get("replied_hash") is None


@pytest.mark.asyncio
async def test_get_offset_replied_raw_target(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """偏移量 N 时返回收集器中的第 N 条消息并记录其 id"""
    from nonebot.adapters.onebot.v11 import Message

    from fake import fake_group_message_event_v11
    from nonebot_plugin_wdym.matcher import get_offset_replied_raw

    await _add_messages(session_factory, "g", 3)
    event = fake_group_message_event_v11(message=Message("/wdym 2"))
    state: dict = {}
    async with session_factory() as session:
        text = await get_offset_replied_raw(state, event, session, "user-1", "g", 2)
    assert text == "msg-1"
    assert state.get("replied_id") is not None


@pytest.mark.asyncio
async def test_get_offset_replied_raw_not_found_finishes(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """偏移量超出收集器记录数时结束流程并提示"""
    from unittest.mock import AsyncMock, patch

    from nonebot.adapters.onebot.v11 import Message

    from fake import fake_group_message_event_v11
    from nonebot_plugin_wdym import matcher

    await _add_messages(session_factory, "g", 1)

    class _NotEnoughMessagesError(Exception):
        pass

    async def _fake_finish(*_args: object, **_kwargs: object) -> None:
        raise _NotEnoughMessagesError

    event = fake_group_message_event_v11(message=Message("/wdym 5"))
    with patch.object(matcher.lang, "finish", new=AsyncMock(side_effect=_fake_finish)):
        with pytest.raises(_NotEnoughMessagesError):
            async with session_factory() as session:
                await matcher.get_offset_replied_raw({}, event, session, "user-1", "g", 5)


@pytest.mark.asyncio
async def test_query_context_messages_with_target_id(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """指定目标 id 时，上下文为目标前 5 条 + 目标本身"""
    from nonebot_plugin_message_summary.models import GroupMessage
    from nonebot_plugin_wdym.matcher import _query_context_messages

    await _add_messages(session_factory, "g", 10)
    async with session_factory() as session:
        target_id = (await session.scalars(select(GroupMessage).where(GroupMessage.message == "msg-7"))).one().id_
        messages = await _query_context_messages(session, "g", target_id=target_id)
    assert [m.message for m in messages] == [f"msg-{i}" for i in range(2, 8)]
