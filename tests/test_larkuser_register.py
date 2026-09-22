"""注册流程昵称兜底的回归测试。

``UserData.nickname`` 是非空列。历史实现中 :func:`get_nickname` 在等待超时、
昵称审查连续不通过时会返回 ``None``，随后被写进 ``UserData`` 并提交，抛出
``IntegrityError: (1048, "Column 'nickname' cannot be null")``。

这里覆盖两件事：

- :func:`get_nickname` 无论用户如何操作都返回非空昵称；
- :func:`register_user` 对空昵称再兜底一次，绝不写入 ``NULL`` / 空白昵称。
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
def patched_lang(monkeypatch):
    """替换 LarkUser 共享的 LangHelper 实例方法，隔离数据库与消息发送"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_larkuser.lang import lang

    sent: list[tuple[str, str]] = []
    finished: list[tuple[str, str]] = []

    async def fake_send(key, user_id, *args, **kwargs):
        sent.append((key, str(user_id)))

    async def fake_finish(key, user_id, *args, **kwargs):
        finished.append((key, str(user_id)))
        raise FinishedException

    async def fake_text(key, user_id, *args, **kwargs):
        return f"text::{key}"

    monkeypatch.setattr(lang, "send", fake_send)
    monkeypatch.setattr(lang, "finish", fake_finish)
    monkeypatch.setattr(lang, "text", fake_text)
    return {"sent": sent, "finished": finished}


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


# ----------------------------------------------------------- get_nickname --


@pytest.mark.asyncio
async def test_get_nickname_prefers_platform_name(monkeypatch, patched_lang):
    """平台能提供昵称时直接使用，不再询问用户"""
    from nonebot_plugin_larkuser.utils import register

    prompt = AsyncMock()
    monkeypatch.setattr(register, "prompt", prompt)

    assert await register.get_nickname(_user_info("小明"), "10001") == ("小明", False)
    prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_nickname_ignores_blank_platform_name(monkeypatch, patched_lang):
    """平台昵称为空白时应继续询问用户，而不是把空白当作昵称"""
    from nonebot_plugin_larkuser.utils import register

    prompt = AsyncMock(return_value="小明")
    monkeypatch.setattr(register, "prompt", prompt)
    monkeypatch.setattr(register, "review_text", AsyncMock(return_value={"conclusion": True, "message": ""}))

    assert await register.get_nickname(_user_info("   "), "10001") == ("小明", True)
    prompt.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["", "   ", "q", "Q"])
async def test_get_nickname_blank_answer_falls_back(answer, monkeypatch, patched_lang):
    """用户留空或发送 q 表示不设置昵称，回退为 用户-{user_id}"""
    from nonebot_plugin_larkuser.utils import register

    monkeypatch.setattr(register, "prompt", AsyncMock(return_value=answer))
    review = AsyncMock()
    monkeypatch.setattr(register, "review_text", review)

    assert await register.get_nickname(_user_info(None), "10001") == ("用户-10001", False)
    review.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_nickname_timeout_falls_back(monkeypatch, patched_lang):
    """等待超时时回退为兜底昵称，并提示用户之后仍可修改"""
    from nonebot_plugin_larkuser.exceptions import PromptTimeout
    from nonebot_plugin_larkuser.utils import register

    monkeypatch.setattr(register, "prompt", AsyncMock(side_effect=PromptTimeout))
    monkeypatch.setattr(register, "review_text", AsyncMock())

    assert await register.get_nickname(_user_info(None), "10001") == ("用户-10001", False)
    assert patched_lang["sent"] == [("input.nickname_failed", "10001")]


@pytest.mark.asyncio
async def test_get_nickname_review_failed_falls_back(monkeypatch, patched_lang):
    """昵称审查连续不通过时回退为兜底昵称，不再返回 None"""
    from nonebot_plugin_larkuser.utils import register

    prompt = AsyncMock(return_value="违规昵称")
    monkeypatch.setattr(register, "prompt", prompt)
    monkeypatch.setattr(register, "review_text", AsyncMock(return_value={"conclusion": False, "message": "违规"}))

    assert await register.get_nickname(_user_info(None), "10001") == ("用户-10001", False)
    assert prompt.await_count == register.NICKNAME_PROMPT_ATTEMPTS
    assert patched_lang["sent"] == [("input.nickname_failed", "10001")]


@pytest.mark.asyncio
async def test_get_nickname_accepts_reviewed_nickname(monkeypatch, patched_lang):
    """审查通过的昵称应去除首尾空白并标记为手动设置（锁定）"""
    from nonebot_plugin_larkuser.utils import register

    monkeypatch.setattr(register, "prompt", AsyncMock(return_value=" 小明 "))
    monkeypatch.setattr(register, "review_text", AsyncMock(return_value={"conclusion": True, "message": ""}))

    assert await register.get_nickname(_user_info(None), "10001") == ("小明", True)


# ---------------------------------------------------------- register_user --


@pytest.mark.asyncio
@pytest.mark.parametrize("nickname_result", [(None, False), ("", False), ("   ", False)])
async def test_register_user_never_writes_null_nickname(nickname_result, monkeypatch, patched_lang, user_session):
    """即使 get_nickname 返回空昵称，也必须写入兜底昵称而不是 NULL"""
    from nonebot_plugin_larkuser.utils import register

    session, factory = user_session
    monkeypatch.setattr(register, "is_user_registered", AsyncMock(return_value=False))
    monkeypatch.setattr(register, "prompt", AsyncMock(return_value=True))
    monkeypatch.setattr(register, "get_nickname", AsyncMock(return_value=nickname_result))

    assert await register.register_user(session, "10001", _user_info(None)) == "用户-10001"

    row = await _load(factory, "10001")
    assert row is not None
    assert row.nickname == "用户-10001"
    assert json.loads(row.config)["lock_nickname"] is False


@pytest.mark.asyncio
async def test_register_user_persists_reviewed_nickname(monkeypatch, patched_lang, user_session):
    """正常路径：写入用户输入并通过审查的昵称，同时锁定昵称"""
    from nonebot_plugin_larkuser.utils import register

    session, factory = user_session
    monkeypatch.setattr(register, "is_user_registered", AsyncMock(return_value=False))
    monkeypatch.setattr(register, "prompt", AsyncMock(return_value=True))
    monkeypatch.setattr(register, "get_nickname", AsyncMock(return_value=("小明", True)))

    assert await register.register_user(session, "10002", _user_info(None)) == "小明"

    row = await _load(factory, "10002")
    assert row is not None
    assert row.nickname == "小明"
    assert json.loads(row.config)["lock_nickname"] is True


@pytest.mark.asyncio
async def test_register_user_cancel_does_not_write(monkeypatch, patched_lang, user_session):
    """用户拒绝最终许可协议时不应写入任何数据"""
    from nonebot.exception import FinishedException
    from nonebot_plugin_larkuser.utils import register

    session, factory = user_session
    monkeypatch.setattr(register, "is_user_registered", AsyncMock(return_value=False))
    monkeypatch.setattr(register, "prompt", AsyncMock(return_value=False))

    with pytest.raises(FinishedException):
        await register.register_user(session, "10003", _user_info(None))

    assert await _load(factory, "10003") is None
    assert patched_lang["finished"] == [("command.cancel", "10003")]
