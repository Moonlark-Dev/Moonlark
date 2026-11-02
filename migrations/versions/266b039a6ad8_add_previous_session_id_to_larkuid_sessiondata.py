"""add previous_session_id to larkuid sessiondata

登录激活（account verify）会轮换 session_id 防 fixation：删除旧会话行、以新 ID
重建。而 /api/login/pending 的长轮询仍拿着旧 ID，旧行删除后鉴权直接 401，前端
把 401 当成「验证超时，请重新登录」。

本迁移给会话行增加 previous_session_id：新会话行指回被轮换掉的旧 ID，
pending 接口在旧 ID 401 时据此把新 ID 交还前端，同时恢复单一迁移历史。

合并 main 上并存的 3 个迁移头：
- e4c1a95f02bd remove openai history record
- 447403958b5a add updates read status
- c6f8a1d2e3b4 add craft equip and merge heads

迁移 ID: 266b039a6ad8
父迁移: e4c1a95f02bd, 447403958b5a, c6f8a1d2e3b4
创建时间: 2026-10-31 12:35:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "266b039a6ad8"
down_revision: str | Sequence[str] | None = (
    "e4c1a95f02bd",
    "447403958b5a",
    "c6f8a1d2e3b4",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "nonebot_plugin_larkuid_sessiondata"
INDEX_NAME = "ix_nonebot_plugin_larkuid_sessiondata_previous_session_id"


def upgrade(name: str = "") -> None:
    if name:
        return
    # 可空列：存量会话没有轮换来源，行为不变。
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.add_column(sa.Column("previous_session_id", sa.String(length=32), nullable=True))
    op.create_index(INDEX_NAME, TABLE_NAME, ["previous_session_id"], unique=False)


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_column("previous_session_id")
