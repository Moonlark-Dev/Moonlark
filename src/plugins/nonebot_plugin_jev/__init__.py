"""nonebot-plugin-jev：封装 TypeSafe Jev（System One）的类型化判断接口

与 nonebot-plugin-openai 一致的组织方式：

- ``config.py`` 读取插件配置（``TYPESAFE_API_KEY`` 等）
- ``lang.py`` + ``src/lang/<lang>/jev.yaml`` 提供本地化提示词
  （问题的 ``instructions`` / ``criteria`` 用 :class:`LangRef` 引用语言键，
  :func:`nonebot_plugin_jev.ask` 在请求前解析）
- ``utils/`` 提供客户端与请求封装

典型用法::

    from nonebot_plugin_jev import ask, noul, lang_ref

    answers = await ask(
        "今天天气真好啊。",
        {"urgent": noul(lang_ref("pre_trigger.help_needed"))},
        lang_str=session.lang_str,
    )
    answers["urgent"].noul  # type: NoulAnswer
"""

from nonebot import require
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-jev",
    description="TypeSafe Jev (System One) 类型化判断接口封装",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")
require("nonebot_plugin_larklang")

from .lang import lang  # noqa: E402, F401
from .types import (  # noqa: E402, F401
    Answer,
    ChoiceAnswer,
    NoulAnswer,
    Question,
    ScoreAnswer,
    choice,
    lang_ref,
    noul,
    score,
)
from .utils.query import JevError, JevNotConfigured, ask, build_payload, resolve_text  # noqa: E402, F401
