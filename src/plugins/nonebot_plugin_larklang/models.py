from pathlib import Path
from pydantic import BaseModel
from nonebot_plugin_orm import Model
from typing import Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class DisplaySetting(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    language: Mapped[str] = mapped_column(String(16), default="zh_hans")
    theme: Mapped[str] = mapped_column(String(16), default="default")


class GroupLanguageSetting(Model):
    """群语言设置模型"""

    group_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    language: Mapped[str] = mapped_column(String(16), default="zh_hans")


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
    # 插件名 -> 键 -> 文本，由 LangLoader 在启动时从 YAML 载入内存
    keys: dict[str, dict[str, LanguageKey]] = {}
