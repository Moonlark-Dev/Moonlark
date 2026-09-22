import pytest
from unittest.mock import AsyncMock, patch

from fake import fake_group_message_event_v11


@pytest.fixture(autouse=True)
def _clean_alias_cache():
    """每个用例前清空全局别名缓存，避免用例间互相污染"""
    from nonebot_plugin_command_alias.__main__ import _alias_names

    _alias_names.clear()
    yield
    _alias_names.clear()


class _FakeSession:
    """模拟 get_session() 的异步上下文管理器，get() 返回预设结果"""

    def __init__(self, row):
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, pk):
        return self.row


async def _run_preprocessor(event, row=None):
    from nonebot_plugin_command_alias.__main__ import apply_command_alias

    with (
        patch("nonebot_plugin_command_alias.__main__.get_main_account", new=AsyncMock(return_value="user-1")),
        patch("nonebot_plugin_command_alias.__main__.get_session", return_value=_FakeSession(row)),
    ):
        await apply_command_alias(event)


async def _run_preprocessor_no_db(event):
    """仅打桩 get_main_account，get_session 保持原样，用于断言不触发数据库查询"""
    from nonebot_plugin_command_alias.__main__ import apply_command_alias

    with patch("nonebot_plugin_command_alias.__main__.get_main_account", new=AsyncMock(return_value="user-1")):
        with patch("nonebot_plugin_command_alias.__main__.get_session") as mocked:
            await apply_command_alias(event)
    return mocked


@pytest.mark.asyncio
async def test_rewrite_first_text_segment() -> None:
    """命中用户别名时，覆写第一个文本段为原指令"""
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_command_alias.models import CommandAlias
    from nonebot_plugin_command_alias.__main__ import _alias_names

    _alias_names.add("c")
    event = fake_group_message_event_v11(message=Message("/c hello world"))
    row = CommandAlias(user_id="user-1", alias="c", command="cave")
    await _run_preprocessor(event, row=row)
    assert event.message[0].data["text"] == "/cave hello world"


@pytest.mark.asyncio
async def test_rewrite_keeps_arguments() -> None:
    """改写后保留原指令参数部分（含多余空格）"""
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_command_alias.models import CommandAlias
    from nonebot_plugin_command_alias.__main__ import _alias_names

    _alias_names.add("cc")
    event = fake_group_message_event_v11(message=Message("/cc  42"))
    row = CommandAlias(user_id="user-1", alias="cc", command="cave")
    await _run_preprocessor(event, row=row)
    assert event.message[0].data["text"] == "/cave  42"


@pytest.mark.asyncio
async def test_no_rewrite_when_alias_not_owned() -> None:
    """别名属于其他用户时不改写"""
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_command_alias.__main__ import _alias_names

    _alias_names.add("c")
    event = fake_group_message_event_v11(message=Message("/c hello"))
    await _run_preprocessor(event, row=None)
    assert event.message[0].data["text"] == "/c hello"


@pytest.mark.asyncio
async def test_no_rewrite_when_word_not_alias() -> None:
    """首词不是已注册别名时不改写（且不查库）"""
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_command_alias.__main__ import _alias_names

    _alias_names.add("c")
    event = fake_group_message_event_v11(message=Message("/cave hello"))
    mocked = await _run_preprocessor_no_db(event)
    mocked.assert_not_called()
    assert event.message[0].data["text"] == "/cave hello"


@pytest.mark.asyncio
async def test_no_rewrite_non_command_message() -> None:
    """不以指令前缀开头的消息不改写（且不查库）"""
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_command_alias.__main__ import _alias_names

    _alias_names.add("c")
    event = fake_group_message_event_v11(message=Message("hello /c"))
    mocked = await _run_preprocessor_no_db(event)
    mocked.assert_not_called()
    assert event.message[0].data["text"] == "hello /c"


@pytest.mark.asyncio
async def test_no_rewrite_alias_command_itself() -> None:
    """/alias 指令本身不被改写（且不查库）"""
    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_command_alias.__main__ import _alias_names

    _alias_names.add("alias")
    event = fake_group_message_event_v11(message=Message("/alias cave c"))
    mocked = await _run_preprocessor_no_db(event)
    mocked.assert_not_called()
    assert event.message[0].data["text"] == "/alias cave c"


@pytest.mark.asyncio
async def test_no_rewrite_non_text_first_segment() -> None:
    """消息第一个文本段之前有图片等非文本段时，仍只改写第一个文本段"""
    from nonebot.adapters.onebot.v11 import Message, MessageSegment
    from nonebot_plugin_command_alias.models import CommandAlias
    from nonebot_plugin_command_alias.__main__ import _alias_names

    _alias_names.add("c")
    event = fake_group_message_event_v11(
        message=Message([MessageSegment.image("https://example.com/a.png"), MessageSegment.text("/c hello")])
    )
    row = CommandAlias(user_id="user-1", alias="c", command="cave")
    await _run_preprocessor(event, row=row)
    assert event.message[1].data["text"] == "/cave hello"


@pytest.mark.asyncio
async def test_db_roundtrip() -> None:
    """真实数据库下：写入别名 → 预处理器命中并改写"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from nonebot.adapters.onebot.v11 import Message
    from nonebot_plugin_command_alias.models import CommandAlias
    from nonebot_plugin_command_alias.__main__ import _alias_names, apply_command_alias

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(CommandAlias.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        session.add(CommandAlias(user_id="user-1", alias="c", command="cave"))
        await session.commit()

    _alias_names.add("c")
    event = fake_group_message_event_v11(message=Message("/c hello"))
    with patch("nonebot_plugin_command_alias.__main__.get_main_account", new=AsyncMock(return_value="user-1")):
        with patch("nonebot_plugin_command_alias.__main__.get_session", return_value=factory()):
            await apply_command_alias(event)
    assert event.message[0].data["text"] == "/cave hello"

    await engine.dispose()


@pytest.mark.asyncio
async def test_variable_name_rule() -> None:
    """别名需遵循变量命名规则"""
    from nonebot_plugin_command_alias.__main__ import _VARIABLE_NAME_RE

    assert _VARIABLE_NAME_RE.fullmatch("c")
    assert _VARIABLE_NAME_RE.fullmatch("cave2")
    assert _VARIABLE_NAME_RE.fullmatch("_my_alias")
    assert not _VARIABLE_NAME_RE.fullmatch("2cave")
    assert not _VARIABLE_NAME_RE.fullmatch("my-alias")
    assert not _VARIABLE_NAME_RE.fullmatch("my alias")
    assert not _VARIABLE_NAME_RE.fullmatch("")
