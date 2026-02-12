from pathlib import Path
from pydantic import BaseModel
from nonebot_plugin_orm import Model
from typing import Optional
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column


class DisplaySetting(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    language: Mapped[str] = mapped_column(String(16), default="zh_hans")
    theme: Mapped[str] = mapped_column(String(16), default="default")


class LanguageKeyCache(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    language: Mapped[str] = mapped_column(String(16))
    plugin: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text())


class LanguageDisplayData(BaseModel):
    hidden: bool = False
    description: str = ""


class LanguageKey(BaseModel):
    text: list[str]
    use_template: bool = True


class LanguageData(BaseModel):
    # 由 Moonlark 自动填入
    path: Path
    # Language 节
    author: str = "Unknown"
    version: str = "latest"
    # 其他节
    display: LanguageDisplayData = LanguageDisplayData()
    patch: Optional[str] = None
