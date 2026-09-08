"""merge migration heads

合并拉取上游后并存的 6 个迁移头，恢复单一迁移历史：
- 5b174323b47f add unreplied count to private chat session
- 9e8893de3642 drop AIWhitelist table
- a3c1e5f7b9d2 remove dropping_enabled from chat_group
- b5c6d7e8f9a1 add egg selection table
- c8d9e0f1a2b3 add auto sign fields to sign_data
- e1f2a3b4c5d6 Add command alias table

迁移 ID: 0841fcf990e5
父迁移: 5b174323b47f, 9e8893de3642, a3c1e5f7b9d2, b5c6d7e8f9a1, c8d9e0f1a2b3, e1f2a3b4c5d6
创建时间: 2026-08-22 11:00:43.000000

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0841fcf990e5"
down_revision: str | Sequence[str] | None = (
    "5b174323b47f",
    "9e8893de3642",
    "a3c1e5f7b9d2",
    "b5c6d7e8f9a1",
    "c8d9e0f1a2b3",
    "e1f2a3b4c5d6",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    pass


def downgrade(name: str = "") -> None:
    pass
