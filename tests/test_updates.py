"""nonebot_plugin_updates 的回归测试。

覆盖：公告 localstore 存取、提醒记录（has_new_update / mark_update_read）、
/updates 指令在 QQ 官方 bot 下发送 markdown + 公告按钮、其他平台渲染为图片。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from nonebot.exception import FinishedException


class _Finished(Exception):
    """用于截断 lang.finish 的哨兵异常"""


class _FakeLang:
    async def text(self, key: str, _user_id: str, *args: object) -> str:
        return key

    async def finish(self, key: str, _user_id: str, *args: object) -> None:
        raise _Finished(key)


_ANNOUNCEMENT = {
    "update_id": 3,
    "title": "测试更新",
    "content": "这是**测试**内容。",
    "buttons": [{"label": "查看", "text": "/updates"}],
    "time": 1000.0,
}


@pytest.fixture
def updates_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from nonebot_plugin_updates import store
    import nonebot_plugin_updates.__main__ as main_module
    from nonebot_plugin_updates.types import UpdateAnnouncement

    monkeypatch.setattr(store, "ANNOUNCEMENT_FILE", tmp_path / "announcement.json")
    monkeypatch.setattr(main_module, "load_announcement", store.load_announcement)
    monkeypatch.setattr(main_module, "mark_update_read", AsyncMock(return_value=None))
    monkeypatch.setattr(main_module, "lang", _FakeLang())
    return store, main_module, UpdateAnnouncement


@pytest.mark.asyncio
async def test_announcement_store_roundtrip(updates_env) -> None:
    """公告保存到 localstore 后可读取；清除后不再存在且清除是幂等的"""
    store, _, _ = updates_env
    assert await store.load_announcement() is None
    assert store.ANNOUNCEMENT_FILE.exists() is False

    announcement = _get_announcement(updates_env)
    await store.save_announcement(announcement)
    loaded = await store.load_announcement()
    assert loaded is not None and loaded.update_id == 3 and loaded.buttons[0].label == "查看"

    await store.clear_announcement()
    assert await store.load_announcement() is None
    await store.clear_announcement()


def _get_announcement(updates_env):
    return updates_env[2].model_validate(_ANNOUNCEMENT)


@pytest.mark.asyncio
async def test_has_new_update_without_file(updates_env) -> None:
    """没有公告时任何人都没有新更新提醒"""
    store, _, _ = updates_env
    from nonebot_plugin_updates.utils import has_new_update

    assert await has_new_update("10001") is False


@pytest.mark.asyncio
async def test_has_new_update_and_mark_read(updates_env) -> None:
    """未阅读的用户有新更新提醒；标记已阅读后提醒消失，发布新版本后重新出现"""
    store, _, _ = updates_env
    from nonebot_plugin_updates.utils import has_new_update, mark_update_read

    await store.save_announcement(_get_announcement(updates_env))
    assert await has_new_update("10001") is True

    await mark_update_read("10001")
    assert await has_new_update("10001") is False

    await store.save_announcement(updates_env[2].model_validate({**_ANNOUNCEMENT, "update_id": 4}))
    assert await has_new_update("10001") is True


@pytest.mark.asyncio
async def test_qq_bot_sends_markdown_with_announcement_buttons(updates_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """QQ 官方 bot：发送 markdown 正文，键盘按钮取自公告配置"""
    store, main_module, _ = updates_env

    sent: list = []

    async def fake_send(self, *_args: object, **_kwargs: object) -> None:
        sent.append(self)

    monkeypatch.setattr(main_module.UniMessage, "send", fake_send)
    # finish() 会抛 FinishedException 终止处理流程，mock 模拟同样行为，防止继续执行图片分支
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(main_module.updates, "finish", finish)
    await store.save_announcement(_get_announcement(updates_env))

    from nonebot.adapters.qq import Bot as QQBot
    from nonebot_plugin_alconna.uniseg import Keyboard

    with pytest.raises(FinishedException):
        await main_module._(bot=MagicMock(spec=QQBot), event=MagicMock(get_user_id=lambda: "openid-1"), user_id="10001")

    assert len(sent) == 1
    keyboard = next(seg for seg in sent[0] if isinstance(seg, Keyboard))
    assert [button.label for button in keyboard.children] == ["查看"]
    assert [button.text for button in keyboard.children] == ["/updates"]
    finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_qq_bot_renders_content_image(updates_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """其他适配器：不发送 keyboard/markdown，正文经 md_to_pic 渲染为图片"""
    store, main_module, _ = updates_env

    send = AsyncMock()
    monkeypatch.setattr(main_module.UniMessage, "send", send)
    monkeypatch.setattr(main_module, "md_to_pic", AsyncMock(return_value=b"image-bytes"))
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(main_module.updates, "finish", finish)
    await store.save_announcement(_get_announcement(updates_env))

    with pytest.raises(FinishedException):
        await main_module._(bot=MagicMock(), event=MagicMock(get_user_id=lambda: "10001"), user_id="10001")

    send.assert_not_awaited()
    finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_announcement_finishes_with_lang(updates_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """没有公告时提示并结束"""
    _, main_module, _ = updates_env

    lang_finish = AsyncMock(side_effect=_Finished("none"))
    monkeypatch.setattr(main_module.lang, "finish", lang_finish)
    send = AsyncMock()
    monkeypatch.setattr(main_module.UniMessage, "send", send)
    finish = AsyncMock()
    monkeypatch.setattr(main_module.updates, "finish", finish)

    from nonebot.adapters.qq import Bot as QQBot

    with pytest.raises(_Finished):
        await main_module._(bot=MagicMock(spec=QQBot), event=MagicMock(get_user_id=lambda: "openid-1"), user_id="10001")

    lang_finish.assert_awaited_once()
    send.assert_not_called()
    finish.assert_not_called()
