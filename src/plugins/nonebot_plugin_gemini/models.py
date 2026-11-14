"""
Gemini 插件数据库模型

与 ``nonebot_plugin_openai.models.OpenAIModelConfig`` 保持同样的结构：一张表同时
保存「默认模型」与「应用（identify）专用模型」，由 ``/gem-model`` 管理。
"""

from nonebot_plugin_orm import Model
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class GeminiModelConfig(Model):
    """Gemini 模型配置表"""

    # 配置项键名，'__default__' 表示默认模型，其他值为应用标识
    config_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    # 模型名称
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 配置类型：'default' 或 'override'
    config_type: Mapped[str] = mapped_column(String(32), default="override")
