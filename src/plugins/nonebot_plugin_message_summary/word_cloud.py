import asyncio
import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from random import Random
from typing import Sequence

import jieba
from wordcloud import WordCloud

from .models import GroupMessage

FONT_PATH = Path("src/static/SarasaGothicSC-Regular.ttf")

# 颜色仅作装饰（词形即标签），只需保证与背景对比度 >= 3:1
WORD_COLORS = ["#2a78d6", "#eb6834", "#008300", "#4a3aa7", "#e34948"]
BACKGROUND_COLOR = "#fcfcfb"

# CQ 码、方括号占位符（如 [图片]）、URL、@ 提及
CLEAN_PATTERNS = re.compile(r"\[[^\]]*\]|https?://\S+|@\S+")
WORD_PATTERN = re.compile(r"[一-鿿A-Za-z]")

STOPWORDS = frozenset(
    [
        "的",
        "了",
        "是",
        "我",
        "你",
        "他",
        "她",
        "它",
        "我们",
        "你们",
        "他们",
        "她们",
        "它们",
        "这",
        "那",
        "这个",
        "那个",
        "这些",
        "那些",
        "这里",
        "那里",
        "在",
        "有",
        "没",
        "没有",
        "就",
        "不",
        "也",
        "都",
        "而",
        "及",
        "与",
        "或",
        "或者",
        "和",
        "跟",
        "被",
        "把",
        "让",
        "给",
        "对",
        "向",
        "从",
        "到",
        "为",
        "因为",
        "所以",
        "但",
        "但是",
        "可是",
        "不过",
        "如果",
        "虽然",
        "然后",
        "还是",
        "还有",
        "就是",
        "只是",
        "只有",
        "而且",
        "并且",
        "于是",
        "因此",
        "其实",
        "什么",
        "怎么",
        "怎么样",
        "为什么",
        "哪",
        "哪个",
        "哪里",
        "谁",
        "多少",
        "几",
        "吗",
        "呢",
        "吧",
        "啊",
        "呀",
        "哦",
        "哈",
        "嗯",
        "呃",
        "诶",
        "唉",
        "嘛",
        "一个",
        "一下",
        "一些",
        "一样",
        "一直",
        "现在",
        "时候",
        "觉得",
        "知道",
        "可以",
        "可能",
        "应该",
        "需要",
        "感觉",
        "东西",
        "事情",
        "问题",
        "自己",
        "大家",
        "别人",
        "所有",
        "已经",
        "真的",
        "不是",
        "不能",
        "不会",
        "不要",
        "有点",
        "比较",
        "非常",
        "很多",
        "这样",
        "那样",
        "这么",
        "那么",
        "出来",
        "起来",
        "下来",
        "上去",
        "过去",
        "回来",
        "看到",
        "说话",
        "今天",
        "明天",
        "昨天",
        "直接",
        "开始",
        "之前",
        "之后",
        "以后",
        "的话",
        "一点",
        "有人",
        "是不是",
        "还要",
        "要不",
        "反正",
        "确实",
        "好像",
        "差不多",
        "多次",
    ],
)


def _extract_words(messages: Sequence[str]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for message in messages:
        text = CLEAN_PATTERNS.sub(" ", message)
        for word in jieba.cut(text):
            word = word.strip().lower()
            if len(word) < 2 or word in STOPWORDS or not WORD_PATTERN.search(word):
                continue
            counter[word] += 1
    return counter


def _color_func(word: str, **_kwargs) -> str:
    # 按词固定取色，同一个词的颜色在多次生成间保持稳定
    return WORD_COLORS[Random(word).randrange(len(WORD_COLORS))]


def _render(frequencies: dict[str, int]) -> bytes:
    cloud = WordCloud(
        font_path=str(FONT_PATH),
        width=1000,
        height=600,
        scale=2,
        background_color=BACKGROUND_COLOR,
        max_words=100,
        prefer_horizontal=0.9,
        color_func=_color_func,
        random_state=42,
    )
    image = cloud.generate_from_frequencies(frequencies).to_image()
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


async def generate_word_cloud(messages: Sequence[GroupMessage]) -> bytes | None:
    """从群消息生成词云图片，无有效词时返回 None"""
    counter = await asyncio.to_thread(_extract_words, [message.message for message in messages])
    if not counter:
        return None
    return await asyncio.to_thread(_render, dict(counter))
