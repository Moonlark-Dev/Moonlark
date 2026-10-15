import jieba
import pypinyin
from typing import Literal

from nonebot.log import logger

BoothillMode = Literal["standard", "fury"]

MA_REPLACEMENT = "他宝贝的"


def _censor_standard(string: str) -> str:
    """标准模式：仅替换拼音以 ma 开头的词。"""
    text = jieba.lcut(string)
    for index, word in enumerate(text):
        syllables = pypinyin.pinyin(word, pypinyin.Style.TONE3)
        if syllables and any(syllable.startswith("ma") for syllable in syllables[0]):
            text[index] = MA_REPLACEMENT
    return "".join(text)


def _censor_fury(string: str) -> str:
    """狂怒模式：沿用现行替换规则（c/q/m/s/b 开头的拼音）。"""
    text = jieba.lcut(string)
    logger.debug(text)
    pinyin = [pypinyin.pinyin(t, pypinyin.Style.TONE3) for t in text]
    logger.debug(pinyin)
    word_to_remove = []

    for f in range(len(pinyin)):
        for k in range(len(pinyin[f])):
            for u in range(len(pinyin[f][k])):
                p = pinyin[f][k][u][0]
                if p in ["c", "q"]:
                    text[f] = "喵"
                elif p == "m":
                    text[f] = MA_REPLACEMENT
                elif p in ["s"]:
                    text[f] = "小可爱"
                    if f != len(pinyin) - 1:
                        word_to_remove.append(f + 1)
                elif p in ["b"] and f not in word_to_remove:
                    text[f] = "可爱"
                    if f != 0:
                        word_to_remove.append(f - 1)
                else:
                    continue
                break
            else:
                continue
            break

    for index in sorted(word_to_remove, reverse=True):
        del text[index]
    return "".join(text)


def censor(string: str, mode: BoothillMode = "standard") -> str:
    if mode == "fury":
        return _censor_fury(string)
    return _censor_standard(string)
