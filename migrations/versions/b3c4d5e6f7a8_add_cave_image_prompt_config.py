"""add cave image prompt user config table

为用户级开关新增表：记录每个用户是否开启「私聊发送单张图片时
询问是否投稿到回声洞」功能，默认关闭。

迁移 ID: b3c4d5e6f7a8
父迁移: d4e5f6a7b8c9
创建时间: 2026-08-03 15:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b3c4d5e6f7a8"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nonebot_plugin_cave_image_prompt_config",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("nonebot_plugin_cave_image_prompt_config")
