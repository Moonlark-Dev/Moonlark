"""merge note type and gal mode heads

合并 #1539（笔记类型/中心词/私密标记）与 #1527（私聊 gal_mode）引入的两个迁移头，
恢复单一迁移历史：
- d6f1a2b3c4e5 add note type, subject and private columns
- ffdcbc994501 add private chat gal mode

迁移 ID: e7a2b9c1d3f4
父迁移: d6f1a2b3c4e5, ffdcbc994501
创建时间: 2026-11-15 15:52:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "e7a2b9c1d3f4"
down_revision: str | Sequence[str] | None = (
    "d6f1a2b3c4e5",
    "ffdcbc994501",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    pass


def downgrade(name: str = "") -> None:
    pass
