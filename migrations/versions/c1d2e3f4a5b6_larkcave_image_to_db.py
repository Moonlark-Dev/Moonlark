"""Migrate larkcave images from local files to database

迁移 ID: c1d2e3f4a5b6
父迁移: b1c2d3e4f5a6
创建时间: 2026-02-09 21:47:00.000000

此迁移将 nonebot_plugin_larkcave_imagedata 表添加 image_data 列，
并将本地存储的图片文件读取后存入数据库。

"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from alembic import op
import sqlalchemy as sa
from nonebot_plugin_localstore import get_data_dir

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return

    bind = op.get_bind()
    dialect = bind.dialect.name

    # 检查表是否存在
    inspector = sa.inspect(bind)
    if not inspector.has_table("nonebot_plugin_larkcave_imagedata"):
        return

    # 1. 添加 image_data 列
    with op.batch_alter_table("nonebot_plugin_larkcave_imagedata", schema=None) as batch_op:
        if dialect == "mysql":
            # MySQL: 使用 LONGBLOB 以支持大图片
            from sqlalchemy.dialects.mysql import LONGBLOB
            batch_op.add_column(sa.Column("image_data", LONGBLOB(), nullable=True))
        else:
            # SQLite: 使用 LargeBinary
            batch_op.add_column(sa.Column("image_data", sa.LargeBinary(), nullable=True))

    # 2. 从本地文件读取图片数据并写入数据库
    data_dir = get_data_dir("nonebot_plugin_larkcave")
    
    # 重新加载表元数据
    metadata = sa.MetaData()
    table = sa.Table("nonebot_plugin_larkcave_imagedata", metadata, autoload_with=bind)

    # 读取所有图片记录
    result = bind.execute(sa.select(table.c.id, table.c.file_id))
    rows = result.fetchall()

    for row in rows:
        image_id = row.id
        file_id = row.file_id
        
        file_path = data_dir.joinpath(file_id)
        if file_path.exists():
            # 读取文件内容
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            
            # 更新数据库
            stmt = table.update().where(table.c.id == image_id).values(image_data=image_bytes)
            bind.execute(stmt)

    bind.commit()


def downgrade(name: str = "") -> None:
    if name:
        return

    bind = op.get_bind()

    # 检查表是否存在
    inspector = sa.inspect(bind)
    if not inspector.has_table("nonebot_plugin_larkcave_imagedata"):
        return

    # 1. 将数据库中的图片数据写回本地文件
    data_dir = get_data_dir("nonebot_plugin_larkcave")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    metadata = sa.MetaData()
    table = sa.Table("nonebot_plugin_larkcave_imagedata", metadata, autoload_with=bind)

    # 读取所有图片记录
    result = bind.execute(sa.select(table.c.id, table.c.file_id, table.c.image_data))
    rows = result.fetchall()

    for row in rows:
        file_id = row.file_id
        image_data = row.image_data
        
        if image_data is not None:
            file_path = data_dir.joinpath(file_id)
            with open(file_path, "wb") as f:
                f.write(image_data)

    # 2. 删除 image_data 列
    with op.batch_alter_table("nonebot_plugin_larkcave_imagedata", schema=None) as batch_op:
        batch_op.drop_column("image_data")
