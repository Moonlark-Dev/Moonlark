"""remove openai history record

迁移 ID: e4c1a95f02bd
父迁移: b7d41f9c2a08
创建时间: 2026-10-18 00:00:00.000000

下线 status report 的 OpenAI 请求记录功能：

- 删除 ``nonebot_plugin_status_report_openaihistoryrecord`` 表及对应模型；
- 移除 ``report_openai_history`` 与 ``/admin/status/openai``、
  ``/admin/status/openai/count`` 接口。

历史请求记录没有需要保留的分析价值，直接删表不迁移。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e4c1a95f02bd"
down_revision: str | Sequence[str] | None = "b7d41f9c2a08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_status_report_openaihistoryrecord"


def upgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table(TABLE_NAME)


def downgrade(name: str = "") -> None:
    if name:
        return
    import sqlalchemy as sa

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("identify", sa.String(length=256), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE_NAME}")),
        info={"bind_key": "nonebot_plugin_status_report"},
    )
