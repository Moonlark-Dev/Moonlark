"""merge all branches

迁移 ID: 74ea37f64bfa
父迁移: 00bcd82b1045, d97df8840d07, dd4f522edf5d, e59556a7ca0c, f92937307e7a
创建时间: 2026-05-10 12:37:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "74ea37f64bfa"
down_revision: str | Sequence[str] | None = (
    "00bcd82b1045",
    "d97df8840d07",
    "dd4f522edf5d",
    "e59556a7ca0c",
    "f92937307e7a",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    pass


def downgrade(name: str = "") -> None:
    pass
