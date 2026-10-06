"""fix chat context message text columns to MEDIUMTEXT on MySQL

迁移 ID: 398dc14b670d
父迁移: 3b9970de1dd4
创建时间: 2026-10-06 23:05:00.000000

修复 ``nonebot_plugin_chat_contextmessage`` 在 MySQL 上的类型漂移:
模型声明的是 ``Text().with_variant(MEDIUMTEXT(), "mysql")``,而建表迁移
(3b9970de1dd4) 用的是 ``sa.Text()`` —— SQLite 下两者等价、CI 不报错,
但生产 MySQL 库里的列是 TEXT(64KB),与模型的 MEDIUMTEXT 不一致,
启动检查报 ``modify_type TEXT() -> Text()`` 并拒绝启动。

将 content / data / tool_calls 三列在 MySQL 上改为 MEDIUMTEXT(16MB),
与模型 ``models.py`` 的 ``CompatibleMediumText`` 对齐;SQLite 无大小差异,跳过。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "398dc14b670d"
down_revision: str | Sequence[str] | None = "3b9970de1dd4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONTEXT_TABLE = "nonebot_plugin_chat_contextmessage"
# (列名, 是否可空) —— 与 models.py 中 ChatContextMessage 的声明一致
COLUMNS: list[tuple[str, bool]] = [
    ("content", False),
    ("data", True),
    ("tool_calls", True),
]


def _alter_columns(type_: sa.types.TypeEngine, existing_types: dict[str, sa.types.TypeEngine]) -> None:
    with op.batch_alter_table(CONTEXT_TABLE, schema=None) as batch_op:
        for column_name, nullable in COLUMNS:
            batch_op.alter_column(
                column_name,
                existing_type=existing_types[column_name],
                type_=type_,
                existing_nullable=nullable,
            )


def upgrade(name: str = "") -> None:
    if name:
        return
    if op.get_bind().dialect.name != "mysql":
        return
    from sqlalchemy.dialects.mysql import MEDIUMTEXT

    _alter_columns(MEDIUMTEXT(), {column: sa.TEXT() for column, _ in COLUMNS})


def downgrade(name: str = "") -> None:
    if name:
        return
    if op.get_bind().dialect.name != "mysql":
        return
    from sqlalchemy.dialects.mysql import MEDIUMTEXT

    _alter_columns(sa.TEXT(), {column: MEDIUMTEXT() for column, _ in COLUMNS})
