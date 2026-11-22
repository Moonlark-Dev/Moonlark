"""添加海龟汤的对局与玩家统计表

迁移 ID: 84571e1c35bd
父迁移: c8d5e3b02f74
创建时间: 2026-11-22 09:21:03.227442

- ``nonebot_plugin_turtle_soup_game``：每个会话最多一条进行中的对局，
  保存谜题 / 问答历史的 JSON、进度、提示下标与过期时间（默认 36 小时）；
- ``nonebot_plugin_turtle_soup_player``：正确作答数，供排行榜与网页榜单使用。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "84571e1c35bd"
down_revision: str | Sequence[str] | None = "c8d5e3b02f74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GAME_TABLE = "nonebot_plugin_turtle_soup_game"
PLAYER_TABLE = "nonebot_plugin_turtle_soup_player"


def upgrade(name: str = "") -> None:
    if name:
        return
    op.create_table(
        GAME_TABLE,
        sa.Column("id_", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("puzzle_data", sa.Text(), nullable=False),
        sa.Column("history_data", sa.Text(), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("asked", sa.Integer(), nullable=False),
        sa.Column("hint_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("expire_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id_", name=op.f(f"pk_{GAME_TABLE}")),
        info={"bind_key": "nonebot_plugin_turtle_soup"},
    )
    op.create_index(
        op.f(f"ix_{GAME_TABLE}_expire_time"),
        GAME_TABLE,
        ["expire_time"],
        unique=False,
    )
    op.create_index(
        op.f(f"ix_{GAME_TABLE}_session_id"),
        GAME_TABLE,
        ["session_id"],
        unique=True,
    )
    op.create_table(
        PLAYER_TABLE,
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("last_correct_time", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("user_id", name=op.f(f"pk_{PLAYER_TABLE}")),
        info={"bind_key": "nonebot_plugin_turtle_soup"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table(PLAYER_TABLE)
    op.drop_table(GAME_TABLE)
