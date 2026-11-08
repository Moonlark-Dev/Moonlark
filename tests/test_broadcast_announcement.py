"""更新公告并入 broadcast 后的回归测试

覆盖：公告 localstore 存取（含旧 updates 文件迁移）、已读提醒记录、
bc 指令展示最新公告。
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def announcement_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from nonebot_plugin_broadcast import announcement

    monkeypatch.setattr(announcement, "ANNOUNCEMENT_FILE", tmp_path / "announcement.json")
    monkeypatch.setattr(announcement, "LEGACY_ANNOUNCEMENT_FILE", tmp_path / "legacy-announcement.json")
    return announcement


_ANNOUNCEMENT = {
    "update_id": 3,
    "title": "测试更新",
    "content": "这是**测试**内容。",
    "buttons": [{"label": "查看", "text": "/bc"}],
    "time": 1000.0,
}


def _get_announcement(announcement_env):
    return announcement_env.UpdateAnnouncement.model_validate(_ANNOUNCEMENT)


@pytest.mark.asyncio
async def test_announcement_store_roundtrip(announcement_env) -> None:
    assert await announcement_env.load_announcement() is None

    await announcement_env.save_announcement(_get_announcement(announcement_env))
    loaded = await announcement_env.load_announcement()
    assert loaded is not None
    assert loaded.update_id == 3
    assert loaded.buttons[0].label == "查看"

    await announcement_env.clear_announcement()
    assert await announcement_env.load_announcement() is None


@pytest.mark.asyncio
async def test_legacy_updates_announcement_is_migrated(announcement_env) -> None:
    """部署后旧 updates 插件的公告文件仍能被读到"""
    announcement_env.LEGACY_ANNOUNCEMENT_FILE.write_text(
        json.dumps(_ANNOUNCEMENT, ensure_ascii=False), encoding="utf-8"
    )

    loaded = await announcement_env.load_announcement()

    assert loaded is not None and loaded.title == "测试更新"
    assert announcement_env.ANNOUNCEMENT_FILE.exists()


@pytest.mark.asyncio
async def test_has_new_update_and_mark_read(announcement_env) -> None:
    await announcement_env.save_announcement(_get_announcement(announcement_env))
    assert await announcement_env.has_new_update("ann-user-1") is True

    await announcement_env.mark_update_read("ann-user-1")
    assert await announcement_env.has_new_update("ann-user-1") is False

    await announcement_env.save_announcement(
        announcement_env.UpdateAnnouncement.model_validate({**_ANNOUNCEMENT, "update_id": 4})
    )
    assert await announcement_env.has_new_update("ann-user-1") is True


@pytest.mark.asyncio
async def test_bc_shows_latest_announcement(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """bc 无参数时展示最新更新公告，并标记为已读（替代原 /updates 指令）"""
    import nonebot_plugin_broadcast.__main__ as module
    from nonebot_plugin_alconna.uniseg import Image
    from nonebot_plugin_broadcast.announcement import UpdateAnnouncement

    monkeypatch.setattr(module, "data_file", tmp_path / "data.json")
    announcement = UpdateAnnouncement.model_validate(_ANNOUNCEMENT)

    class FakeLang:
        async def text(self, key: str, _user_id: str, *args: object) -> str:
            return key

        async def finish(self, key: str, _user_id: str, *args: object) -> None:
            raise AssertionError(f"unexpected finish: {key}")

    finish = AsyncMock()
    mark_read = AsyncMock()
    monkeypatch.setattr(module, "lang", FakeLang())
    monkeypatch.setattr(module, "load_announcement", AsyncMock(return_value=announcement))
    monkeypatch.setattr(module, "mark_update_read", mark_read)
    monkeypatch.setattr(module, "md_to_pic", AsyncMock(return_value=b"image-bytes"))
    monkeypatch.setattr(module, "get_event_group_key", AsyncMock(return_value="12345"))
    monkeypatch.setattr(module.bc_cmd, "finish", finish)

    await module.handle_bc(event=MagicMock(), action="", user_id="ann-user-2")

    finish.assert_awaited_once()
    message = finish.await_args.args[0]
    assert any(isinstance(segment, Image) for segment in message)
    mark_read.assert_awaited_once_with("ann-user-2")


@pytest.mark.asyncio
async def test_bc_in_private_chat_shows_announcement(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """私聊里也能用 bc 查看更新公告（原 /updates 的用法不能因为合并而丢失）"""
    import nonebot_plugin_broadcast.__main__ as module
    from nonebot_plugin_broadcast.announcement import UpdateAnnouncement

    monkeypatch.setattr(module, "data_file", tmp_path / "data.json")
    announcement = UpdateAnnouncement.model_validate(_ANNOUNCEMENT)

    class FakeLang:
        async def text(self, key: str, _user_id: str, *args: object) -> str:
            return key

        async def finish(self, key: str, _user_id: str, *args: object) -> None:
            raise AssertionError(f"unexpected finish: {key}")

    finish = AsyncMock()
    mark_read = AsyncMock()
    monkeypatch.setattr(module, "lang", FakeLang())
    monkeypatch.setattr(module, "load_announcement", AsyncMock(return_value=announcement))
    monkeypatch.setattr(module, "mark_update_read", mark_read)
    monkeypatch.setattr(module, "md_to_pic", AsyncMock(return_value=b"image-bytes"))
    monkeypatch.setattr(module, "get_event_group_key", AsyncMock(return_value=None))
    monkeypatch.setattr(module.bc_cmd, "finish", finish)

    await module.handle_bc(event=MagicMock(), action="", user_id="ann-user-3")

    finish.assert_awaited_once()
    mark_read.assert_awaited_once_with("ann-user-3")
