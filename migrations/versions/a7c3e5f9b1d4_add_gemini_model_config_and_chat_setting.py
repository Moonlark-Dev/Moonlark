"""add gemini model config table and chat global setting

迁移 ID: a7c3e5f9b1d4
父迁移: b7e4c1a2d9f0
创建时间: 2026-11-14 15:50:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a7c3e5f9b1d4"
down_revision: str | Sequence[str] | None = "b7e4c1a2d9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        "nonebot_plugin_gemini_geminimodelconfig",
        sa.Column("config_key", sa.String(length=256), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("config_type", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("config_key", name=op.f("pk_nonebot_plugin_gemini_geminimodelconfig")),
        info={"bind_key": "nonebot_plugin_gemini"},
    )
    op.create_table(
        "nonebot_plugin_chat_chatglobalsetting",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_nonebot_plugin_chat_chatglobalsetting")),
        info={"bind_key": "nonebot_plugin_chat"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_chat_chatglobalsetting")
    op.drop_table("nonebot_plugin_gemini_geminimodelconfig")
