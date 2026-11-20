"""merge trade and chat heads

合并 main 上遗留的双头，恢复单一迁移历史：
- b836ade52b29 add trade market
- 619748a690eb add chat group enhance

迁移 ID: b7f4c2a91e63
父迁移: b836ade52b29, 619748a690eb
创建时间: 2026-11-20 23:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "b7f4c2a91e63"
down_revision: str | Sequence[str] | None = (
    "b836ade52b29",
    "619748a690eb",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    pass


def downgrade(name: str = "") -> None:
    pass
