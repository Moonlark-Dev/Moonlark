"""add_diarypost table and migrate diary data from note

迁移 ID: b4c5d6e7f8a9
父迁移: a3f8c2d1e5b7
创建时间: 2026-06-08 15:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import (
    bindparam,
    column,
    delete as sa_delete,
    func,
    insert as sa_insert,
    select,
    table,
)

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a3f8c2d1e5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DIARYPOST_TABLE = "nonebot_plugin_chat_diarypost"
NOTE_TABLE = "nonebot_plugin_chat_note"
DIARY_CONTEXT_ID = "moonlark_diary"


def upgrade(name: str = "") -> None:
    if name:
        return

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "mysql":
        table_check = sa.text("SHOW TABLES LIKE :table_name")
    else:
        table_check = sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name")
    result = bind.execute(table_check, {"table_name": DIARYPOST_TABLE}).fetchall()
    if result:
        # 表已存在（之前迁移部分执行过），跳过
        return

    # 1. 创建 DiaryPost 表
    op.create_table(
        DIARYPOST_TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("keywords", sa.String(256), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expire_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table(DIARYPOST_TABLE, schema=None) as batch_op:
        batch_op.create_index(f"ix_{DIARYPOST_TABLE}_created_at", ["created_at"])

    # 2. 将 note 表中 context_id='moonlark_diary' 的数据迁移到 diarypost
    # created_time 是 Float 类型的 Unix 时间戳，需要转换为 DateTime
    # MySQL 用 FROM_UNIXTIME()，SQLite 用 datetime(..., 'unixepoch', 'localtime')
    diarypost = table(
        DIARYPOST_TABLE,
        column("content"),
        column("keywords"),
        column("created_at"),
        column("expire_at"),
    )
    note = table(
        NOTE_TABLE,
        column("content"),
        column("keywords"),
        column("created_time"),
        column("expire_time"),
        column("context_id"),
    )
    if dialect == "mysql":
        created_at_col = func.from_unixtime(note.c.created_time)
    else:
        created_at_col = func.datetime(
            note.c.created_time, sa.literal_column("'unixepoch'"), sa.literal_column("'localtime'")
        )
    select_stmt = select(note.c.content, func.coalesce(note.c.keywords, ""), created_at_col, note.c.expire_time).where(
        note.c.context_id == bindparam("context_id")
    )
    insert_stmt = sa_insert(diarypost).from_select(
        ["content", "keywords", "created_at", "expire_at"],
        select_stmt,
    )
    bind.execute(insert_stmt, {"context_id": DIARY_CONTEXT_ID})

    # 3. 删除已迁移的 note 记录
    delete_stmt = sa_delete(note).where(note.c.context_id == bindparam("context_id"))
    bind.execute(delete_stmt, {"context_id": DIARY_CONTEXT_ID})


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(DIARYPOST_TABLE, schema=None) as batch_op:
        batch_op.drop_index(f"ix_{DIARYPOST_TABLE}_created_at")

    op.drop_table(DIARYPOST_TABLE)
