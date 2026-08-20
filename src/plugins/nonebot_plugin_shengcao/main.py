import json
import random
from pathlib import Path

import jieba
from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id, review_text

lang = LangHelper()

alc = Alconna("grass", Args["text?", str])
grass_cmd = on_alconna(alc)

_dict_data: dict = {}


def _load_dict() -> None:
    global _dict_data
    path = Path(__file__).parent / "data" / "shengcao_dict.json"
    with open(path, "r", encoding="utf-8") as f:
        _dict_data = json.load(f)


_load_dict()


def shengcao_text(text: str) -> str:
    words = list(jieba.cut(text))
    result = []
    for w in words:
        if w.strip() and w in _dict_data:
            entry = _dict_data[w]
            same = entry.get("same_word", [])
            similar = entry.get("similar_word", [])
            if same and similar:
                pool = same if random.random() < 0.6 else similar
            elif same:
                pool = same
            elif similar:
                pool = similar
            else:
                pool = None
            if pool:
                result.append(random.choice(pool))
            else:
                result.append(w)
        else:
            result.append(w)
    return "".join(result)


@grass_cmd.handle()
async def _(text: str | None = None, user_id: str = get_user_id()) -> None:
    if not text or not text.strip():
        await lang.finish("empty", user_id)
    output_text = shengcao_text(text)
    if not (result := await review_text(output_text))["compliance"]:
        await lang.finish("review_failed", user_id)
    await lang.finish("result", user_id, output_text)
