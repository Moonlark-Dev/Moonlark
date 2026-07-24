"""Add main account mapping table

迁移 ID: ffdcbc994499
父迁移: ffdcbc994498
创建时间: 2026-07-24 17:31:00.000000

将 Main Account 的映射数据从文件存储迁移到数据库表
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "ffdcbc994499"
down_revision: str | Sequence[str] | None = "ffdcbc994498"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "nonebot_plugin_larkutils_mainaccountmapping"

# 命名约定: {plugin_name}_{snake_case_class_name}
# MainAccountMapping -> mainaccountmapping


def upgrade(name: str = "") -> None:
    if name:
        return

    # 创建主账号映射表
    op.create_table(
        TABLE_NAME,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("main_account", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # 注意：文件数据的迁移通过 subaccount.py 中的 on_startup 钩子完成


def downgrade(name: str = "") -> None:
    if name:
        return

    # 删除表
    op.drop_table(TABLE_NAME)

    # 注意：downgrade 不会恢复文件，数据通过文件系统保留
