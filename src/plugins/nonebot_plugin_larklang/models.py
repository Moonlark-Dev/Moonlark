from pathlib import Path
from sqlalchemy import String
from nonebot_plugin_orm import Model
from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column


class LanguageLockData(BaseModel):
    enable: bool = False
    price: int = 0


class LanguageDisplayData(BaseModel):
    hidden: bool = False
    description: str = ""


class LanguagePatchData(BaseModel):
    patch: bool = False
    base: str = "zh_hans"


class LanguageKey(BaseModel):
    text: list[str]
    use_template: bool = True


class LanguageData(BaseModel):
    # 由 Moonlark 自动填入
    path: Path
    keys: dict[str, dict[str, dict[str, LanguageKey]]] = {}
    # Language 节
    author: str = "Unknown"
    version: str = "latest"
    # 其他节
    lock: LanguageLockData = LanguageLockData()
    display: LanguageDisplayData = LanguageDisplayData()
    patch: LanguagePatchData = LanguagePatchData()


class LanguageConfig(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    language: Mapped[str] = mapped_column(String(16))
