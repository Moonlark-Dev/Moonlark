from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy.orm import mapped_column, Mapped


class Bag(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bag_index: Mapped[int]
    user_id: Mapped[str]
    item_id: Mapped[str]
    count: Mapped[int]
    locked: Mapped[bool]
    data: Mapped[bytes]     # b64 json


class BagOverflow(Model):
    id_: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str]
    item_id: Mapped[str]
    count: Mapped[int]
    data: Mapped[bytes]     # b64 json
    time: Mapped[datetime]
