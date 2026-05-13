"""add dropping_enabled to chat_group

迁移 ID: 69e42fc34f38
父迁移: 74ea37f64bfa
创建时间: 2026-05-13 11:54:20.256050

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = '69e42fc34f38'
down_revision: str | Sequence[str] | None = '74ea37f64bfa'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table('nonebot_plugin_chat_chatgroup', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dropping_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')))


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table('nonebot_plugin_chat_chatgroup', schema=None) as batch_op:
        batch_op.drop_column('dropping_enabled')
