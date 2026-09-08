"""drop AIWhitelist table

AI 功能白名单已移除，所有节点（含 QQ 官方适配器）均可使用 AI 功能，
白名单表不再使用，予以删除。

迁移 ID: 9e8893de3642
父迁移: ffdcbc994498
创建时间: 2026-08-24 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "9e8893de3642"
down_revision: str | Sequence[str] | None = "ffdcbc994498"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    conn = op.get_bind()
    inspector = inspect(conn)
    # 兼容从未创建过该表的数据库（如全新部署）
    if "nonebot_plugin_openai_aiwhitelist" in inspector.get_table_names():
        op.drop_table("nonebot_plugin_openai_aiwhitelist")


def downgrade(name: str = "") -> None:
    if name:
        return
    conn = op.get_bind()
    inspector = inspect(conn)
    if inspector.has_table("nonebot_plugin_openai_aiwhitelist"):
        return
    op.create_table(
        "nonebot_plugin_openai_aiwhitelist",
        sa.Column("group_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("group_id", name=op.f("pk_nonebot_plugin_openai_aiwhitelist")),
        info={"bind_key": "nonebot_plugin_openai"},
    )
