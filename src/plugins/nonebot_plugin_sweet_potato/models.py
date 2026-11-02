from nonebot_plugin_orm import Model
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class SweetPotatoStat(Model):
    """玩家的烫手山芋累计数据（用于排行）。"""

    __tablename__ = "nonebot_plugin_sweet_potato_stat"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # 成功捂热次数：hold 未爆炸，且之后成功把山芋传出去
    successful_holds: Mapped[int] = mapped_column(default=0)
    # 累计成功捂热次数（含尚未完成传递的）
    total_holds: Mapped[int] = mapped_column(default=0)
    total_passes: Mapped[int] = mapped_column(default=0)
    burn_count: Mapped[int] = mapped_column(default=0)
    game_count: Mapped[int] = mapped_column(default=0)
