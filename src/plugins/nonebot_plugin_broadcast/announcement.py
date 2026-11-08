"""更新公告

原 ``nonebot_plugin_updates`` 插件已整体并入 broadcast：公告的存储、Web 发布
接口与已读记录都在这里，查看入口改为 ``bc`` 指令。
"""

import json

from aiofiles import open as aio_open
from nonebot import require
from pydantic import BaseModel

require("nonebot_plugin_localstore")
require("nonebot_plugin_orm")

from nonebot_plugin_localstore import get_data_file  # noqa: E402
from nonebot_plugin_orm import get_session  # noqa: E402

from .models import UpdateReadStatus  # noqa: E402

ANNOUNCEMENT_FILE = get_data_file("nonebot_plugin_broadcast", "announcement.json")
# 旧 updates 插件留下的公告文件：首次读取时自动迁移到 broadcast 的数据目录
LEGACY_ANNOUNCEMENT_FILE = get_data_file("nonebot_plugin_updates", "announcement.json")


class UpdateButton(BaseModel):
    """按钮配置：点击后会把 text 作为指令文本发回群聊"""

    label: str
    text: str


class UpdateAnnouncement(BaseModel):
    """更新公告：正文为 markdown，可附带按钮"""

    update_id: int
    title: str
    content: str
    buttons: list[UpdateButton] = []
    time: float


class UpdateAnnouncementInput(BaseModel):
    """超管通过网页端提交的更新公告"""

    title: str
    content: str
    buttons: list[UpdateButton] = []


def build_markdown(announcement: UpdateAnnouncement, at_user: str = "") -> str:
    """把公告渲染为 markdown 文本"""
    at = f"{at_user}\n\n" if at_user else ""
    return f"{at}## {announcement.title}\n\n{announcement.content}"


async def _migrate_legacy_announcement() -> None:
    """把旧 updates 插件的公告文件搬到 broadcast 数据目录（只搬一次）"""
    if ANNOUNCEMENT_FILE.exists() or not LEGACY_ANNOUNCEMENT_FILE.exists():
        return
    try:
        async with aio_open(LEGACY_ANNOUNCEMENT_FILE, encoding="utf-8") as legacy:
            content = await legacy.read()
        ANNOUNCEMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        async with aio_open(ANNOUNCEMENT_FILE, "w", encoding="utf-8") as current:
            await current.write(content)
        # 迁移成功后删除旧文件：否则用户清空公告后，旧公告会被再次搬回来
        LEGACY_ANNOUNCEMENT_FILE.unlink(missing_ok=True)
    except OSError:
        # 迁移失败不影响新公告功能，只是旧公告暂时看不到
        pass


async def load_announcement() -> UpdateAnnouncement | None:
    """读取本地保存的最新更新公告；未发布过或文件损坏时返回 None"""
    await _migrate_legacy_announcement()
    if not ANNOUNCEMENT_FILE.exists():
        return None
    try:
        async with aio_open(ANNOUNCEMENT_FILE, encoding="utf-8") as f:
            data = json.loads(await f.read())
        return UpdateAnnouncement.model_validate(data)
    except (json.JSONDecodeError, ValueError, OSError):
        return None


async def save_announcement(announcement: UpdateAnnouncement) -> None:
    """保存更新公告到本地文件"""
    async with aio_open(ANNOUNCEMENT_FILE, "w", encoding="utf-8") as f:
        await f.write(announcement.model_dump_json())


async def clear_announcement() -> None:
    """清除当前更新公告"""
    ANNOUNCEMENT_FILE.unlink(missing_ok=True)


async def has_new_update(user_id: str) -> bool:
    """判断用户是否有未阅读的最新更新公告"""
    announcement = await load_announcement()
    if announcement is None:
        return False
    async with get_session() as session:
        data = await session.get(UpdateReadStatus, user_id)
    return data is None or data.last_update_id != announcement.update_id


async def mark_update_read(user_id: str) -> None:
    """将最新更新公告标记为已阅读"""
    announcement = await load_announcement()
    if announcement is None:
        return
    async with get_session() as session:
        data = await session.get(UpdateReadStatus, user_id)
        if data is None:
            session.add(UpdateReadStatus(user_id=user_id, last_update_id=announcement.update_id))
        elif data.last_update_id != announcement.update_id:
            data.last_update_id = announcement.update_id
        else:
            return
        await session.commit()
