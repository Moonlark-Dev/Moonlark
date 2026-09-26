from nonebot_plugin_orm import Model
from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class MarketItem(Model):
    """市场中的一条上架记录

    同一物品允许同时存在多条记录（来自不同的卖家），`item_id` 即 `market list` 中
    展示的商品编号，可以用于 `market buy <编号>`。
    """

    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_namespace: Mapped[str] = mapped_column(String(64))
    remain_count: Mapped[int]
    # 显式指定 Float()：SQLAlchemy 2.1 起 Mapped[float] 的默认映射由 Float 变为 Double，
    # 不写显式类型会让 nb orm check 把现有 FLOAT 列判成待迁移
    price: Mapped[float] = mapped_column(Float())
    user_id: Mapped[str] = mapped_column(String(128))
    item_data: Mapped[str] = mapped_column(Text())  # json


class SellLog(Model):
    """按物品类型累计的成交记录，用于计算平均成交价"""

    item_namespace: Mapped[str] = mapped_column(String(64), primary_key=True)
    sold_count: Mapped[int]
    price_sum: Mapped[float] = mapped_column(Float())
