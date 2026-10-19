"""merge main heads

合并主分支新增的迁移头，恢复单一迁移历史：
- b7d41f9c2a08 add favor judge record
- b8e2f1a4c7d9 move qq group to plugin
- 447403958b5a add updates read status

迁移 ID: f2a96c4be153
父迁移: b7d41f9c2a08, b8e2f1a4c7d9
创建时间: 2026-10-15 07:58:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "f2a96c4be153"
down_revision: str | Sequence[str] | None = (
    "b7d41f9c2a08",
    "b8e2f1a4c7d9",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    pass


def downgrade(name: str = "") -> None:
    pass
