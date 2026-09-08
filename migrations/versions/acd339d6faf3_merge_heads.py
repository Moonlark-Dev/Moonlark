"""merge remaining heads

迁移 ID: acd339d6faf3
父迁移: 878331db0e57, 62be9ecbd765, 7f8a9b0c1d2e, bc900b880f83
创建时间: 2026-07-11 20:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "acd339d6faf3"
down_revision: str | Sequence[str] | None = (
    "878331db0e57",
    "62be9ecbd765",
    "7f8a9b0c1d2e",
    "bc900b880f83",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    pass


def downgrade(name: str = "") -> None:
    pass
