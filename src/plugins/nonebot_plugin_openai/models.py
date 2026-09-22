"""
OpenAI 插件数据库模型
存储模型配置，替代原有的 JSON 文件存储
"""

from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text


class OpenAIModelConfig(Model):
    """OpenAI 模型配置表"""

    # 配置项键名，'default' 表示默认模型，其他值为应用标识
    config_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    # 模型名称
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 配置类型：'default' 或 'override'
    config_type: Mapped[str] = mapped_column(String(32), default="override")
