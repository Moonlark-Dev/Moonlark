"""Drop language key cache table

迁移 ID: f0a1b2c3d4e5
父迁移: 8a7b8160f2f7
创建时间: 2026-09-21 00:00:00.000000

larklang 的语言键缓存已由数据库改为进程内存（LanguageData.keys），
不再需要 nonebot_plugin_larklang_languagekeycache 表。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | Sequence[str] | None = "8a7b8160f2f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_larklang_languagekeycache"


def upgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table(TABLE_NAME)


def downgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("plugin", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("language", "plugin", "key", name=op.f(f"pk_{TABLE_NAME}")),
        info={"bind_key": "nonebot_plugin_larklang"},
    )
