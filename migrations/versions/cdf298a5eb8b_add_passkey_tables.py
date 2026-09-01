"""add passkey tables

迁移 ID: cdf298a5eb8b
父迁移: c3760946c865
创建时间: 2026-08-30 10:00:00.000000

为 Passkey（WebAuthn）登录新增凭据表与一次性挑战表。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "cdf298a5eb8b"
down_revision: str | Sequence[str] | None = "c3760946c865"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    # 用户注册的 Passkey 公钥凭据
    op.create_table(
        "nonebot_plugin_larkuid_passkeycredential",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("device_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nonebot_plugin_larkuid_passkeycredential")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_nonebot_plugin_larkuid_passkeycredential_credential_id")),
        info={"bind_key": "nonebot_plugin_larkuid"},
    )
    op.create_index(
        op.f("ix_nonebot_plugin_larkuid_passkeycredential_user_id"),
        "nonebot_plugin_larkuid_passkeycredential",
        ["user_id"],
        unique=False,
        info={"bind_key": "nonebot_plugin_larkuid"},
    )
    # 一次性 WebAuthn 挑战
    op.create_table(
        "nonebot_plugin_larkuid_passkeychallenge",
        sa.Column("challenge", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("origin", sa.String(length=256), nullable=False),
        sa.Column("rp_id", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("challenge", name=op.f("pk_nonebot_plugin_larkuid_passkeychallenge")),
        info={"bind_key": "nonebot_plugin_larkuid"},
    )


def downgrade(name: str = "") -> None:
    if name:
        return
    op.drop_table("nonebot_plugin_larkuid_passkeychallenge")
    op.drop_index(
        op.f("ix_nonebot_plugin_larkuid_passkeycredential_user_id"),
        table_name="nonebot_plugin_larkuid_passkeycredential",
    )
    op.drop_table("nonebot_plugin_larkuid_passkeycredential")
