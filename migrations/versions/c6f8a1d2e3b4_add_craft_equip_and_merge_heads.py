"""add craft & equip tables and merge migration heads

迁移 ID: c6f8a1d2e3b4
父迁移: b7d41f9c2a08 + b8e2f1a4c7d9（合并 main 当前两个迁移分支）
创建时间: 2026-10-14 12:00:00.000000

1. 合并 main 当前两个并行的迁移分支（b7d41f9c2a08 与 b8e2f1a4c7d9），
   保证迁移历史回到单一 head；
2. 给鸡蛋新机制新增三张表：

- nonebot_plugin_craft_machine：合成机等级（等级决定可同时进行的合成数量）；
- nonebot_plugin_craft_job：合成机中正在进行的合成任务；
- nonebot_plugin_equip_equipped：装备栏（每种装备类型同时只能装备一件）。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c6f8a1d2e3b4"
down_revision: str | Sequence[str] | None = ("b7d41f9c2a08", "b8e2f1a4c7d9")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MACHINE_TABLE = "nonebot_plugin_craft_machine"
JOB_TABLE = "nonebot_plugin_craft_job"
EQUIPPED_TABLE = "nonebot_plugin_equip_equipped"


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "mysql":
        result = bind.execute(sa.text("SHOW TABLES LIKE :table_name"), {"table_name": name}).fetchall()
    else:
        result = bind.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"), {"table_name": name}
        ).fetchall()
    return bool(result)


def upgrade(name: str = "") -> None:
    if name:
        return

    if not _table_exists(MACHINE_TABLE):
        op.create_table(
            MACHINE_TABLE,
            sa.Column("user_id", sa.String(length=128), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
            sa.PrimaryKeyConstraint("user_id"),
        )

    if not _table_exists(JOB_TABLE):
        op.create_table(
            JOB_TABLE,
            sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=128), nullable=False),
            sa.Column("recipe_id", sa.String(length=64), nullable=False),
            sa.Column("time", sa.DateTime(), nullable=False),
            sa.Column("finish_time", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id_"),
        )
        op.create_index(op.f("ix_nonebot_plugin_craft_job_user_id"), JOB_TABLE, ["user_id"])
        op.create_index(op.f("ix_nonebot_plugin_craft_job_finish_time"), JOB_TABLE, ["finish_time"])

    if not _table_exists(EQUIPPED_TABLE):
        op.create_table(
            EQUIPPED_TABLE,
            sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=128), nullable=False),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("item_id", sa.String(length=64), nullable=False),
            sa.Column("data", sa.Text(), nullable=False),
            sa.Column("time", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id_"),
        )
        op.create_index(op.f("ix_nonebot_plugin_equip_equipped_user_id"), EQUIPPED_TABLE, ["user_id"])


def downgrade(name: str = "") -> None:
    if name:
        return

    op.drop_table(EQUIPPED_TABLE)
    op.drop_table(JOB_TABLE)
    op.drop_table(MACHINE_TABLE)
