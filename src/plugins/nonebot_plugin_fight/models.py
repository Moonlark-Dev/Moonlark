from datetime import datetime
from typing import Literal, Optional
from nonebot_plugin_orm import Model
from pydantic import BaseModel
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, Text


class Character(Model):
    character_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128))
    get_time: Mapped[datetime]
    character_type: Mapped[int]
    experience: Mapped[int]
    hp_percent: Mapped[int]
    fav: Mapped[float] = mapped_column(default=0)
    buff_list: Mapped[bytes] = mapped_column(default=b"[]")
    equipment: Mapped[bytes] = mapped_column(default=b"{}")
    talent_level: Mapped[bytes] = mapped_column(default=b"{}")
    weapon_experience: Mapped[int]
    weapon_damage: Mapped[int]


class EquipmentData(Model):
    equipment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    equipment_type: Mapped[int]
    experience: Mapped[int]
    user_id: Mapped[str] = mapped_column(String(128))
    gains: Mapped[bytes] = mapped_column(default=b"{}")


class PlayerTeam(Model):
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    characters: Mapped[bytes] = mapped_column(default=b"[]")
    name: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
