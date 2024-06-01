import jieba
import pypinyin
from nonebot.log import logger


def censor(string: str) -> str:
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
                    text[f] = "他宝贝的"
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
