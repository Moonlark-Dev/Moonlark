"""add_diarypost table and migrate diary data from note

迁移 ID: b4c5d6e7f8a9
父迁移: a3f8c2d1e5b7
创建时间: 2026-06-08 15:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

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

    # 1. 创建 DiaryPost 表
    op.create_table(
        DIARYPOST_TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("keywords", sa.String(256), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expire_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table(DIARYPOST_TABLE, schema=None) as batch_op:
        batch_op.create_index(f"ix_{DIARYPOST_TABLE}_created_at", ["created_at"])

    # 2. 将 note 表中 context_id='moonlark_diary' 的数据迁移到 diarypost
    #    title 从 keywords 中取（日期 + "日记"），expire_time 映射到 expire_at
    op.execute(f"""
        INSERT INTO {DIARYPOST_TABLE} (title, content, keywords, created_at, expire_at)
        SELECT
            COALESCE(keywords, '') AS title,
            content,
            COALESCE(keywords, ''),
            datetime(created_time, 'unixepoch', 'localtime'),
            expire_time
        FROM {NOTE_TABLE}
        WHERE context_id = '{DIARY_CONTEXT_ID}'
    """)

    # 3. 删除已迁移的 note 记录
    op.execute(f"DELETE FROM {NOTE_TABLE} WHERE context_id = '{DIARY_CONTEXT_ID}'")


def downgrade(name: str = "") -> None:
    if name:
        return
    with op.batch_alter_table(DIARYPOST_TABLE, schema=None) as batch_op:
        batch_op.drop_index(f"ix_{DIARYPOST_TABLE}_created_at")

    op.drop_table(DIARYPOST_TABLE)
