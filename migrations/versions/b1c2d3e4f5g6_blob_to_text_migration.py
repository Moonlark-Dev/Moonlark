"""Convert BLOB columns to TEXT for JSON storage

迁移 ID: b1c2d3e4f5g6
父迁移: a0af598a2bca
创建时间: 2026-02-09 19:17:00.000000

此迁移将以下表中的 BLOB 列改为 TEXT 类型，并转换已存储的数据：
- nonebot_plugin_fight_character: buff_list, equipment, talent_level
- nonebot_plugin_fight_equipmentdata: gains
- nonebot_plugin_fight_playerteam: character_list
- nonebot_plugin_larkuser_userdata: config (需要 base64 解码)
- nonebot_plugin_larklang_languagekeycache: text
- nonebot_plugin_bag_bag: data (需要 base64 解码)
- nonebot_plugin_bag_bagoverflow: data (需要 base64 解码)

"""

from __future__ import annotations

import base64
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5g6"
down_revision: str | Sequence[str] | None = "a0af598a2bca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return

    bind = op.get_bind()
    dialect = bind.dialect.name

    # ========== nonebot_plugin_fight_character ==========
    # 这些列存储的是直接 encode 的 JSON（如 b"[]"），需要解码为字符串
    _migrate_blob_to_text(
        bind,
        dialect,
        "nonebot_plugin_fight_character",
        ["buff_list", "equipment", "talent_level"],
        pk_column="character_id",
        decode_base64=False,
    )

    # ========== nonebot_plugin_fight_equipmentdata ==========
    _migrate_blob_to_text(
        bind, dialect, "nonebot_plugin_fight_equipmentdata", ["gains"], pk_column="equipment_id", decode_base64=False
    )

    # ========== nonebot_plugin_fight_playerteam ==========
    _migrate_blob_to_text(
        bind, dialect, "nonebot_plugin_fight_playerteam", ["character_list"], pk_column="user_id", decode_base64=False
    )

    # ========== nonebot_plugin_larkuser_userdata ==========
    # config 列使用 base64 编码存储，需要解码
    _migrate_blob_to_text(
        bind, dialect, "nonebot_plugin_larkuser_userdata", ["config"], pk_column="user_id", decode_base64=True
    )

    # ========== nonebot_plugin_larklang_languagekeycache ==========
    # text 列存储的是直接 encode 的 JSON
    _migrate_blob_to_text(
        bind, dialect, "nonebot_plugin_larklang_languagekeycache", ["text"], pk_column="id_", decode_base64=False
    )

    # ========== nonebot_plugin_bag_bag ==========
    # data 列使用 base64 编码存储
    _migrate_blob_to_text(bind, dialect, "nonebot_plugin_bag_bag", ["data"], pk_column="id_", decode_base64=True)

    # ========== nonebot_plugin_bag_bagoverflow ==========
    # data 列使用 base64 编码存储
    _migrate_blob_to_text(
        bind, dialect, "nonebot_plugin_bag_bagoverflow", ["data"], pk_column="id_", decode_base64=True
    )


def _migrate_blob_to_text(
    bind, dialect: str, table_name: str, columns: list[str], pk_column: str, decode_base64: bool = False
) -> None:
    """迁移 BLOB 列到 TEXT 并转换数据

    Args:
        bind: 数据库连接
        dialect: 数据库方言 (mysql, sqlite)
        table_name: 表名
        columns: 需要转换的列名列表
        pk_column: 主键列名
        decode_base64: 是否需要 base64 解码
    """
    # 检查表是否存在
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return

    # 1. 首先读取所有现有数据
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)

    # 读取所有行
    select_cols = [table.c[pk_column]] + [table.c[col] for col in columns]
    result = bind.execute(sa.select(*select_cols))
    rows = result.fetchall()

    # 2. 修改列类型
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        for col in columns:
            if dialect == "mysql":
                batch_op.alter_column(col, existing_type=sa.LargeBinary(), type_=sa.Text(), existing_nullable=False)
            else:  # SQLite
                batch_op.alter_column(col, existing_type=sa.LargeBinary(), type_=sa.Text(), existing_nullable=False)

    # 3. 转换并更新数据
    # 重新加载表元数据以获取新的列类型
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)

    for row in rows:
        pk_value = getattr(row, pk_column)
        updates = {}

        for col in columns:
            old_value = getattr(row, col)
            if old_value is None:
                continue

            # 转换数据
            if isinstance(old_value, bytes):
                if decode_base64:
                    try:
                        new_value = base64.b64decode(old_value).decode("utf-8")
                    except Exception:
                        # 如果 base64 解码失败，尝试直接解码
                        new_value = old_value.decode("utf-8")
                else:
                    new_value = old_value.decode("utf-8")
            else:
                # 已经是字符串，不需要转换
                new_value = old_value

            updates[col] = new_value

        if updates:
            stmt = table.update().where(table.c[pk_column] == pk_value).values(**updates)
            bind.execute(stmt)

    bind.commit()


def downgrade(name: str = "") -> None:
    if name:
        return

    bind = op.get_bind()
    dialect = bind.dialect.name

    # ========== nonebot_plugin_bag_bagoverflow ==========
    _migrate_text_to_blob(
        bind, dialect, "nonebot_plugin_bag_bagoverflow", ["data"], pk_column="id_", encode_base64=True
    )

    # ========== nonebot_plugin_bag_bag ==========
    _migrate_text_to_blob(bind, dialect, "nonebot_plugin_bag_bag", ["data"], pk_column="id_", encode_base64=True)

    # ========== nonebot_plugin_larklang_languagekeycache ==========
    _migrate_text_to_blob(
        bind, dialect, "nonebot_plugin_larklang_languagekeycache", ["text"], pk_column="id_", encode_base64=False
    )

    # ========== nonebot_plugin_larkuser_userdata ==========
    _migrate_text_to_blob(
        bind, dialect, "nonebot_plugin_larkuser_userdata", ["config"], pk_column="user_id", encode_base64=True
    )

    # ========== nonebot_plugin_fight_playerteam ==========
    _migrate_text_to_blob(
        bind, dialect, "nonebot_plugin_fight_playerteam", ["character_list"], pk_column="user_id", encode_base64=False
    )

    # ========== nonebot_plugin_fight_equipmentdata ==========
    _migrate_text_to_blob(
        bind, dialect, "nonebot_plugin_fight_equipmentdata", ["gains"], pk_column="equipment_id", encode_base64=False
    )

    # ========== nonebot_plugin_fight_character ==========
    _migrate_text_to_blob(
        bind,
        dialect,
        "nonebot_plugin_fight_character",
        ["buff_list", "equipment", "talent_level"],
        pk_column="character_id",
        encode_base64=False,
    )


def _migrate_text_to_blob(
    bind, dialect: str, table_name: str, columns: list[str], pk_column: str, encode_base64: bool = False
) -> None:
    """回滚：将 TEXT 列改回 BLOB 并转换数据

    Args:
        bind: 数据库连接
        dialect: 数据库方言 (mysql, sqlite)
        table_name: 表名
        columns: 需要转换的列名列表
        pk_column: 主键列名
        encode_base64: 是否需要 base64 编码
    """
    # 检查表是否存在
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return

    # 1. 首先读取所有现有数据
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)

    # 读取所有行
    select_cols = [table.c[pk_column]] + [table.c[col] for col in columns]
    result = bind.execute(sa.select(*select_cols))
    rows = result.fetchall()

    # 2. 修改列类型
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        for col in columns:
            batch_op.alter_column(col, existing_type=sa.Text(), type_=sa.LargeBinary(), existing_nullable=False)

    # 3. 转换并更新数据
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)

    for row in rows:
        pk_value = getattr(row, pk_column)
        updates = {}

        for col in columns:
            old_value = getattr(row, col)
            if old_value is None:
                continue

            # 转换数据
            if isinstance(old_value, str):
                if encode_base64:
                    new_value = base64.b64encode(old_value.encode("utf-8"))
                else:
                    new_value = old_value.encode("utf-8")
            else:
                # 已经是 bytes，不需要转换
                new_value = old_value

            updates[col] = new_value

        if updates:
            stmt = table.update().where(table.c[pk_column] == pk_value).values(**updates)
            bind.execute(stmt)

    bind.commit()
