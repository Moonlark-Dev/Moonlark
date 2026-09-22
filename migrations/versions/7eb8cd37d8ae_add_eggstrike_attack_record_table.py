"""add eggstrike attack record table

迁移 ID: 7eb8cd37d8ae
父迁移: a9e4b2c8f1d6
创建时间: 2026-08-02 18:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "7eb8cd37d8ae"
down_revision: str | Sequence[str] | None = "a9e4b2c8f1d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_eggstrike_attackrecord"


def upgrade(name: str = "") -> None:
    if name:
        return

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "mysql":
        table_check = sa.text("SHOW TABLES LIKE :table_name")
    else:
        table_check = sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name")
    result = bind.execute(table_check, {"table_name": TABLE_NAME}).fetchall()
    if result:
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("egg_id", sa.String(length=128), nullable=False),
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id_", name=op.f("pk_nonebot_plugin_eggstrike_attackrecord")),
    )
    op.create_index(
        op.f("ix_nonebot_plugin_eggstrike_attackrecord_user_id"),
        TABLE_NAME,
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_nonebot_plugin_eggstrike_attackrecord_target_id"),
        TABLE_NAME,
        ["target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_nonebot_plugin_eggstrike_attackrecord_time"),
        TABLE_NAME,
        ["time"],
        unique=False,
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_index(op.f("ix_nonebot_plugin_eggstrike_attackrecord_time"), table_name=TABLE_NAME)
    op.drop_index(op.f("ix_nonebot_plugin_eggstrike_attackrecord_target_id"), table_name=TABLE_NAME)
    op.drop_index(op.f("ix_nonebot_plugin_eggstrike_attackrecord_user_id"), table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
