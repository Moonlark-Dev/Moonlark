"""兼容模块：markdown 消息图床已拆分到 :mod:`nonebot_plugin_larkutils.image_host`

两种模式（对象存储 / 自建图床）的具体实现与选择逻辑见 ``image_host`` 包。
"""

from .image_host import create_image_markdown as create_image_markdown

__all__ = ["create_image_markdown"]
