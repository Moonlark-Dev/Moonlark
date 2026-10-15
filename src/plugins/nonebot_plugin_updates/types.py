from pydantic import BaseModel


class UpdateButton(BaseModel):
    """按钮配置：点击设备会把 text 作为指令文本发回群聊"""

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
