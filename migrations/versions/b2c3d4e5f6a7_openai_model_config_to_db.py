"""Migrate OpenAI model config from JSON to database

迁移 ID: b2c3d4e5f6a7
父迁移: ffdcbc994494
创建时间: 2026-02-21 11:30:00.000000

将 OpenAI 插件的模型配置从 JSON 文件迁移到数据库表
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "ffdcbc994494"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "nonebot_plugin_openai_modelconfig"


def upgrade(name: str = "") -> None:
    if name:
        return

    # ### 创建表结构 ###
    op.create_table(
        TABLE_NAME,
        sa.Column("config_key", sa.String(length=256), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("config_type", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("config_key"),
    )

    # 注意：数据迁移通过 on_startup 钩子完成，不在此处处理


def downgrade(name: str = "") -> None:
    if name:
        return

    # ### 删除表 ###
    op.drop_table(TABLE_NAME)

    # 注意：downgrade 不会恢复 JSON 文件，数据需要通过其他方式恢复
