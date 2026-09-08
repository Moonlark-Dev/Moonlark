import pytest
from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from fake import fake_group_message_event_v11


def _fake_bot():
    """最小化的 OneBot V11 Bot 替身，供 UniMessage 转换使用"""
    bot = MagicMock()
    bot.adapter.get_name.return_value = "OneBot V11"
    return bot


def _image_only_message():
    from nonebot.adapters.onebot.v11 import Message, MessageSegment

    return Message([MessageSegment.image("https://example.com/a.png")])


def _image_with_text_message():
    from nonebot.adapters.onebot.v11 import Message, MessageSegment

    return Message([MessageSegment.image("https://example.com/a.png"), MessageSegment.text("看看这张图")])


@pytest.fixture
async def engine():
    from nonebot_plugin_larkcave.models import CaveImagePromptConfig

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(CaveImagePromptConfig.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(CaveImagePromptConfig.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.fixture
async def patched_get_session(monkeypatch, db_session):
    """把插件内的 get_session 替换为测试专用的 session"""
    from nonebot_plugin_larkcave.commands import prompt as mod

    def fake_get_session(**kwargs):
        return db_session

    monkeypatch.setattr(mod, "get_session", fake_get_session)


@pytest.mark.asyncio
async def test_message_with_single_image() -> None:
    """单图片消息返回 True，图片+文本返回 False"""
    from nonebot_plugin_larkcave.commands.prompt import message_with_single_image

    event = fake_group_message_event_v11(message=_image_only_message())
    assert message_with_single_image(event, _fake_bot()) is True

    event = fake_group_message_event_v11(message=_image_with_text_message())
    assert message_with_single_image(event, _fake_bot()) is False


@pytest.mark.asyncio
async def test_prompt_disabled_by_default(patched_get_session) -> None:
    """没有配置记录时默认关闭，投稿询问不会触发"""
    from nonebot_plugin_larkcave.commands.prompt import is_prompt_enabled

    assert await is_prompt_enabled(user_id="user-1") is False


@pytest.mark.asyncio
async def test_prompt_enabled_after_user_toggle(patched_get_session, db_session) -> None:
    """用户开启后投稿询问生效"""
    from nonebot_plugin_larkcave.commands.prompt import is_prompt_enabled
    from nonebot_plugin_larkcave.models import CaveImagePromptConfig

    db_session.add(CaveImagePromptConfig(user_id="user-1", enabled=True))
    await db_session.commit()

    assert await is_prompt_enabled(user_id="user-1") is True


@pytest.mark.asyncio
async def test_prompt_disabled_after_user_toggle_off(patched_get_session, db_session) -> None:
    """用户再次关闭后投稿询问不再生效"""
    from nonebot_plugin_larkcave.commands.prompt import is_prompt_enabled
    from nonebot_plugin_larkcave.models import CaveImagePromptConfig

    db_session.add(CaveImagePromptConfig(user_id="user-1", enabled=True))
    await db_session.commit()
    assert await is_prompt_enabled(user_id="user-1") is True

    entry = await db_session.get(CaveImagePromptConfig, "user-1")
    entry.enabled = False
    await db_session.commit()

    assert await is_prompt_enabled(user_id="user-1") is False
