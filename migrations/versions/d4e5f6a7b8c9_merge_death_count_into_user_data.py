"""merge death_count into UserData and drop UserDeathRecord

迁移 ID: d4e5f6a7b8c9
父迁移: 7eb8cd37d8ae
创建时间: 2026-08-02 20:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "7eb8cd37d8ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_TABLE = "nonebot_plugin_larkuser_userdata"
RECORD_TABLE = "nonebot_plugin_larkuser_userdeathrecord"


def upgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(DATA_TABLE, schema=None) as batch_op:
        batch_op.add_column(sa.Column("death_count", sa.Integer(), nullable=False, server_default="0"))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE nonebot_plugin_larkuser_userdata SET death_count = "
            "(SELECT r.death_count FROM nonebot_plugin_larkuser_userdeathrecord r "
            "WHERE r.user_id = nonebot_plugin_larkuser_userdata.user_id) "
            "WHERE EXISTS (SELECT 1 FROM nonebot_plugin_larkuser_userdeathrecord r "
            "WHERE r.user_id = nonebot_plugin_larkuser_userdata.user_id)",
        ),
    )
    op.drop_table(RECORD_TABLE)


def downgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        RECORD_TABLE,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("death_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_nonebot_plugin_larkuser_userdeathrecord")),
        info={"bind_key": "nonebot_plugin_larkuser"},
    )
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO nonebot_plugin_larkuser_userdeathrecord (user_id, death_count) "
            "SELECT user_id, death_count FROM nonebot_plugin_larkuser_userdata WHERE death_count > 0",
        ),
    )
    with op.batch_alter_table(DATA_TABLE, schema=None) as batch_op:
        batch_op.drop_column("death_count")
