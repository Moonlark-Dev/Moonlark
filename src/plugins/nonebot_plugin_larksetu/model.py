from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from nonebot_plugin_orm import Model

class UserData(Model):
    user_id: Mapped[str] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column(default=0)

class ImageUrlData(BaseModel):
    original: str

class ImageData(BaseModel):
    pid: int
    p: int
    uid: int
    title: str
    author: str
    r18: bool
    width: int
    height: int
    tags: list[str]
    ext: str
    aiType: int
    uploadDate: int
    urls: ImageUrlData

class LoliconResponse(BaseModel):
    error: str
    data: list[ImageData]