from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    """真实 sqlite 内存库，建好 Message Summary 与 chat 插件的表"""
    from nonebot_plugin_message_summary.models import GroupMessage

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(GroupMessage.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def master_config(monkeypatch) -> str:
    """把主人账号配置为测试用的 user id，返回该 id"""
    from nonebot_plugin_chat.config import config

    monkeypatch.setattr(config, "chat_master_user_id", "10086")
    return "10086"


async def _add_messages(
    session_factory: async_sessionmaker[AsyncSession],
    group_id: str,
    user_id: str,
    nickname: str,
    count: int = 1,
    *,
    hours_ago: float = 0.0,
) -> None:
    from nonebot_plugin_message_summary.models import GroupMessage

    timestamp = datetime.now() - timedelta(hours=hours_ago)
    async with session_factory() as session:
        for index in range(count):
            session.add(
                GroupMessage(
                    message=f"{user_id}-{index}",
                    sender_nickname=nickname,
                    user_id=user_id,
                    group_id=group_id,
                    timestamp=timestamp + timedelta(seconds=index),
                ),
            )
        await session.commit()


async def _add_group(session_factory: async_sessionmaker[AsyncSession], group_id: str) -> None:
    from nonebot_plugin_chat.models import ChatGroup

    async with session_factory() as session:
        session.add(ChatGroup(group_id=group_id, enabled=True))
        await session.commit()


@pytest.mark.asyncio
async def test_recent_speakers_top5_within_12h(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """只统计 12 小时内的发言，按条数降序取前 5，昵称取该成员最近一条记录"""
    from nonebot_plugin_chat.utils.session_metadata import get_recent_speakers

    await _add_messages(session_factory, "qq_1", "u-a", "a-old", 4)
    await _add_messages(session_factory, "qq_1", "u-a", "a", 1)
    await _add_messages(session_factory, "qq_1", "u-b", "b", 4)
    await _add_messages(session_factory, "qq_1", "u-c", "c", 3)
    await _add_messages(session_factory, "qq_1", "u-d", "d", 2)
    await _add_messages(session_factory, "qq_1", "u-e", "e", 1)
    # 12 小时以外的发言与其它群的发言都不应出现
    await _add_messages(session_factory, "qq_1", "u-old", "old", 9, hours_ago=13)
    await _add_messages(session_factory, "qq_2", "u-other", "other", 9)

    async with session_factory() as session:
        speakers = await get_recent_speakers("qq_1", session=session)
    assert speakers == ["a", "b", "c", "d", "e"]


@pytest.mark.asyncio
async def test_recent_speakers_empty_group(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from nonebot_plugin_chat.utils.session_metadata import get_recent_speakers

    async with session_factory() as session:
        assert await get_recent_speakers("qq_1", session=session) == []


@pytest.mark.asyncio
async def test_master_present_is_sticky(session_factory: async_sessionmaker[AsyncSession], master_config: str) -> None:
    """主人在消息记录里出现过就落库为 True，清空消息记录后依旧为 True"""
    from nonebot_plugin_chat.models import ChatGroup
    from nonebot_plugin_chat.utils.session_metadata import is_master_present
    from nonebot_plugin_message_summary.models import GroupMessage

    await _add_group(session_factory, "qq_1")
    await _add_messages(session_factory, "qq_1", master_config, "XiaoDeng3386", 1)

    async with session_factory() as session:
        assert await is_master_present("qq_1", session=session) is True
        group = await session.get(ChatGroup, {"group_id": "qq_1"})
        assert group is not None and group.master_present is True

    async with session_factory() as session:
        await session.execute(delete(GroupMessage).where(GroupMessage.group_id == "qq_1"))
        await session.commit()
        assert await is_master_present("qq_1", session=session) is True


@pytest.mark.asyncio
async def test_master_present_matches_nickname_and_is_group_scoped(
    monkeypatch, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """配置成昵称也能命中；其它群出现过主人不影响本群"""
    from nonebot_plugin_chat.config import config
    from nonebot_plugin_chat.utils.session_metadata import is_master_present

    monkeypatch.setattr(config, "chat_master_user_id", "XiaoDeng3386")
    await _add_group(session_factory, "qq_1")
    await _add_group(session_factory, "qq_2")
    await _add_messages(session_factory, "qq_2", "10086", "XiaoDeng3386", 1)

    async with session_factory() as session:
        assert await is_master_present("qq_2", session=session) is True
        assert await is_master_present("qq_1", session=session) is False


@pytest.mark.asyncio
async def test_master_absent_keeps_false(session_factory: async_sessionmaker[AsyncSession], master_config: str) -> None:
    from nonebot_plugin_chat.models import ChatGroup
    from nonebot_plugin_chat.utils.session_metadata import is_master_present

    await _add_group(session_factory, "qq_1")
    await _add_messages(session_factory, "qq_1", "u-b", "b", 2)

    async with session_factory() as session:
        assert await is_master_present("qq_1", session=session) is False
        group = await session.get(ChatGroup, {"group_id": "qq_1"})
        assert group is not None and group.master_present is False


@pytest.mark.asyncio
async def test_master_present_disabled_without_config(
    monkeypatch, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """未配置 CHAT_MASTER_USER_ID 时不做判定"""
    from nonebot_plugin_chat.config import config
    from nonebot_plugin_chat.utils.session_metadata import is_master_present

    monkeypatch.setattr(config, "chat_master_user_id", "")
    await _add_group(session_factory, "qq_1")
    await _add_messages(session_factory, "qq_1", "10086", "XiaoDeng3386", 1)

    async with session_factory() as session:
        assert await is_master_present("qq_1", session=session) is False


@pytest.mark.asyncio
async def test_build_group_session_metadata_lines(
    session_factory: async_sessionmaker[AsyncSession], master_config: str
) -> None:
    from nonebot_plugin_chat.utils.session_metadata import build_group_session_metadata

    await _add_group(session_factory, "qq_1")
    await _add_messages(session_factory, "qq_1", master_config, "XiaoDeng3386", 3)
    await _add_messages(session_factory, "qq_1", "u-b", "b", 2)

    async with session_factory() as session:
        lines = await build_group_session_metadata("qq_1", session=session)
    assert lines == [
        "当前会话成员/最近发言者：XiaoDeng3386、b……",
        "XiaoDeng3386 是否在当前会话：是",
    ]


@pytest.mark.asyncio
async def test_build_group_session_metadata_without_master_config(
    monkeypatch, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from nonebot_plugin_chat.config import config
    from nonebot_plugin_chat.utils.session_metadata import build_group_session_metadata

    monkeypatch.setattr(config, "chat_master_user_id", "")
    await _add_group(session_factory, "qq_1")
    await _add_messages(session_factory, "qq_1", "u-b", "b", 1)

    async with session_factory() as session:
        lines = await build_group_session_metadata("qq_1", session=session)
    assert lines == ["当前会话成员/最近发言者：b……"]
