"""add message_hash to GroupMessage

迁移 ID: 7f8a9b0c1d2e
父迁移: ffdcbc994494
创建时间: 2026-07-04 20:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import LargeBinary, inspect

revision: str = "7f8a9b0c1d2e"
down_revision: str | Sequence[str] | None = "ffdcbc994494"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("nonebot_plugin_message_summary_groupmessage")]
    dialect = conn.dialect.name

    if "message_hash" in columns:
        # 列已被 auto-migration 创建，SQLite 上类型不对需要修正
        if dialect == "sqlite":
            with op.batch_alter_table("nonebot_plugin_message_summary_groupmessage") as batch_op:
                batch_op.alter_column(
                    "message_hash",
                    existing_type=sa.NUMERIC(precision=32),
                    type_=LargeBinary(32),
                    existing_nullable=True,
                )
        # MySQL 上 BINARY(32) 已经是正确的，无需操作
    else:
        # 列不存在，创建
        hash_type = LargeBinary(32) if dialect == "sqlite" else sa.BINARY(32)
        op.add_column(
            "nonebot_plugin_message_summary_groupmessage",
            sa.Column("message_hash", hash_type, nullable=True),
        )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_column("nonebot_plugin_message_summary_groupmessage", "message_hash")
