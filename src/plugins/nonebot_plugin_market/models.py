from datetime import datetime
from typing import Optional
from nonebot_plugin_orm import Model
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class MarketItem(Model):
    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_namespace: Mapped[str] = mapped_column(String(64))
    remain_count: Mapped[int]
    price: Mapped[float]
    user_id: Mapped[str] = mapped_column(String(128))
    item_data: Mapped[bytes]

class SellLog(Model):
    item_namespace: Mapped[str] = mapped_column(String(64), primary_key=True)
    sold_count: Mapped[int]
    price_sum: Mapped[float]
