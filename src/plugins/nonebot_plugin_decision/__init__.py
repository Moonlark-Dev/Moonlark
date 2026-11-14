"""nonebot-plugin-decision：封装 OpenRouter Decisions API 的类型化决策接口

与 nonebot-plugin-openai 一致的组织方式：

- ``config.py`` 读取插件配置（``DECISION_API_KEY`` 等）
- ``lang.py`` + ``src/lang/<lang>/decision.yaml`` 提供本地化提示词
  （问题的 ``instructions`` / ``criteria`` 用 :class:`LangRef` 引用语言键，
  :func:`nonebot_plugin_decision.ask` 在请求前解析）
- ``utils/`` 提供客户端与请求封装

典型用法::

    from nonebot_plugin_decision import ask, noul, lang_ref

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
    name="nonebot-plugin-decision",
    description="OpenRouter Decisions API 类型化决策接口封装",
    usage="",
    config=Config,
)

require("nonebot_plugin_orm")  # ruff: ignore[non-empty-init-module]
require("nonebot_plugin_larklang")  # ruff: ignore[non-empty-init-module]

from .lang import lang  # ruff: ignore[module-import-not-at-top-of-file]
from .types import (  # ruff: ignore[module-import-not-at-top-of-file]
    Answer,
    BoxAnswer,
    BoxCoords,
    ChoiceAnswer,
    LangRef,
    NoulAnswer,
    Question,
    QuestionType,
    ScoreAnswer,
    box,
    choice,
    lang_ref,
    noul,
    score,
)
from .utils.query import (  # ruff: ignore[module-import-not-at-top-of-file]
    DecisionError,
    DecisionNotConfiguredError,
    ask,
    build_payload,
    resolve_endpoint,
    resolve_text,
)

__all__ = [
    "Answer",
    "BoxAnswer",
    "BoxCoords",
    "ChoiceAnswer",
    "DecisionError",
    "DecisionNotConfiguredError",
    "LangRef",
    "NoulAnswer",
    "Question",
    "QuestionType",
    "ScoreAnswer",
    "ask",
    "box",
    "build_payload",
    "choice",
    "lang",
    "lang_ref",
    "noul",
    "resolve_endpoint",
    "resolve_text",
    "score",
]
