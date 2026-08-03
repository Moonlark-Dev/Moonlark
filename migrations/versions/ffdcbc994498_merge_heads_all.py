"""merge all remaining heads

合并 3 个悬垂头，修复 revision 树分支混乱导致的 CI 报错。
InstantMemoryCache 的创建（e7f8a9b0c1d2）和删除（ffdcbc994495）
位于不同分支，拓扑排序可能先执行删除导致「no such table」错误。

迁移 ID: ffdcbc994498
父迁移: 3ee8b001fa91, 7203628bbc6c, ffdcbc994497
创建时间: 2026-07-23 14:18:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "ffdcbc994498"
down_revision: str | Sequence[str] | None = (
    "3ee8b001fa91",
    "7203628bbc6c",
    "ffdcbc994497",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    conn = op.get_bind()
    inspector = inspect(conn)
    # 安全网：如果 ffdcbc994495 在 e7f8a9b0c1d2 之前执行
    # （表未创建），此处的兜底删除保证最终状态没有此表
    if "nonebot_plugin_chat_instantmemorycache" in inspector.get_table_names():
        op.drop_table("nonebot_plugin_chat_instantmemorycache")


def downgrade(name: str = "") -> None:
    pass
