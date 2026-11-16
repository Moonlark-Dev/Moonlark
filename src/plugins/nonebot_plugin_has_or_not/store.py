"""题目生成、本地缓存与去重。

题目由 ``nonebot_plugin_openai`` 调用模型生成，一次生成一小批并缓存在 LocalStore
的数据目录里。为了“短期内不重复出题”，这里做两层防护：

1. 生成时把近期出过的答案与六个词语组合写进追加的 user 消息，明确要求模型避开；
2. 生成结束后再做一次本地过滤：答案（归一化后）或六个词语组合与近期重复的直接丢弃。

因此即使模型无视了第 1 层的约束，也不会把重复题目写进缓存。
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from pathlib import Path
from typing import Optional

import aiofiles
from nonebot import logger
from nonebot_plugin_larkutils import escape_markdown
from nonebot_plugin_localstore import get_data_file
from nonebot_plugin_openai import fetch_json, generate_message
from nonebot_plugin_openai.utils.message import get_message

from .config import config
from .types import GeneratedQuestion, QuestionStoreData

# 生成题目时追加给模型的约束（系统提示词本体不修改，只追加一条 user 消息）
_GENERATION_IDENTIFY = "Has Or Not (Generate)"
# 追加约束里最多列多少个近期答案 / 词语组合，避免提示词无限增长
_MAX_PROMPT_EXCLUSIONS = 30
_MAX_PROMPT_WORD_SETS = 10
# 六个词里有几个与近期题目相同时视为近似重复
_NEAR_DUPLICATE_WORDS = 5


class QuestionGenerationError(RuntimeError):
    """模型没有给出任何可用且不重复的题目"""


def normalize_answer(value: str) -> str:
    """归一化答案，用于本地精确比对与去重。

    - NFKC：全角字符转半角（``ｏ`` -> ``o``、``＋`` -> ``+``）；
    - 小写：``O`` 与 ``o`` 视为相同；
    - 去掉全部空白。

    不删除标点：答案本身可能就是 ``!``、``?``、``<`` 这类特殊符号，删掉后既会
    误判无法作答，也会让去重指纹变得不可靠。
    """
    text = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"\s+", "", text)


def is_exact_match(guess: str, answer: str) -> bool:
    """不做语义判断的快速精确匹配（大小写、全半角、句读不敏感）。"""
    return normalize_answer(guess) == normalize_answer(answer)


def question_word_signature(question: GeneratedQuestion) -> tuple[str, ...]:
    """六个词语的归一化指纹：同一组词换个答案也算重复题目。"""
    return tuple(sorted(normalize_answer(word) for pair in question.prompts for word in (pair.contain, pair.missing)))


def is_valid_question(question: GeneratedQuestion) -> bool:
    """检查题目结构是否满足出题规则（三项、六个非空且互不相同的词、答案不直接出现在词上）。"""
    answer = normalize_answer(question.answer)
    if not answer or len(question.prompts) != 3 or _has_line_break(question.answer):
        return False
    words: list[str] = []
    for pair in question.prompts:
        if _has_line_break(pair.contain) or _has_line_break(pair.missing):
            return False
        contain, missing = normalize_answer(pair.contain), normalize_answer(pair.missing)
        if not contain or not missing or contain == missing:
            return False
        words.extend([contain, missing])
    if len(set(words)) != 6:
        return False
    # 规则要求答案不能直接出现在词语上
    return all(answer not in word for word in words)


def _has_line_break(value: str) -> bool:
    return "\n" in value or "\r" in value


def filter_questions(
    candidates: list[GeneratedQuestion],
    known_answers: list[str],
    known_word_sets: list[list[str]],
) -> list[GeneratedQuestion]:
    """过滤结构不合法、答案重复或词语组合重复的题目（批内重复同样会过滤）。

    除了完全相同的一组词，六个词里有五个与近期题目相同也视为重复：这类题目
    基本只是把某一道旧题换了个答案，属于模型“短期内重复出题”的常见形态。
    """
    seen_answers = set(known_answers)
    seen_word_sets: list[set[str]] = [set(word_set) for word_set in known_word_sets]
    accepted: list[GeneratedQuestion] = []
    for question in candidates:
        if not is_valid_question(question):
            continue
        answer = normalize_answer(question.answer)
        word_set = set(question_word_signature(question))
        if answer in seen_answers or any(len(word_set & known) >= _NEAR_DUPLICATE_WORDS for known in seen_word_sets):
            continue
        seen_answers.add(answer)
        seen_word_sets.append(word_set)
        accepted.append(question)
    return accepted


def format_question(question: GeneratedQuestion, escape: bool = True) -> str:
    """按通用两行对照格式渲染题目（用于非 QQ 官方适配器的图片渲染与纯文本回退）。

    默认转义 Markdown 特殊字符，避免模型生成的词语带 ``*`` 等字符时破坏排版。
    """
    escaper = escape_markdown if escape else (lambda value: value)
    contains = " ".join(escaper(pair.contain.strip()) for pair in question.prompts)
    missing = " ".join(escaper(pair.missing.strip()) for pair in question.prompts)
    return f"**有无有无**\n⭕：{contains}\n❌：{missing}"


def format_question_table(question: GeneratedQuestion, escape: bool = True) -> str:
    """按 QQ 官方机器人的 Markdown 表格样式渲染题目。"""
    escaper = escape_markdown if escape else (lambda value: value)
    rows = [
        "| ⭕ 有 | ❌ 无 |",
        "| ----------- | ----------- |",
    ]
    for pair in question.prompts:
        contain = escaper(pair.contain.strip())
        missing = escaper(pair.missing.strip())
        rows.append(f"| {contain} | {missing} |")
    return "\n".join(rows)


def build_generation_extra(exclusions: list[str], word_sets: list[list[str]], count: int) -> str:
    """构造追加在系统提示词后面的 user 消息（系统提示词本体保持不变）。"""
    lines = [
        "请再额外遵守以下要求：",
        (
            f"1. 把 {count} 个题目放进一个 JSON 数组中，数组的每一项都是上面规定格式的题目对象；"
            "不要输出任何其他内容，不要使用 Markdown 代码块。"
        ),
    ]
    recent_answers = [answer for answer in exclusions[-_MAX_PROMPT_EXCLUSIONS:] if answer]
    if recent_answers:
        lines.append("2. 以下答案近期已经出过，请勿重复使用：" + "、".join(recent_answers))
    recent_word_sets = [word_set for word_set in word_sets[-_MAX_PROMPT_WORD_SETS:] if word_set]
    if recent_word_sets:
        lines.append(
            "3. 不要与以下近期题目使用完全相同的六个词语："
            + "；".join("/".join(word_set) for word_set in recent_word_sets)
        )
    return "\n".join(lines)


async def generate_questions(exclusions: list[str], word_sets: list[list[str]], count: int) -> list[GeneratedQuestion]:
    """调用 OpenAI 插件生成一批题目。"""
    messages = [
        await get_message("system", "has_or_not/system.md.jinja"),
        generate_message(build_generation_extra(exclusions, word_sets, count), "user"),
    ]
    return await fetch_json(
        messages,
        list[GeneratedQuestion],
        identify=_GENERATION_IDENTIFY,
        timeout=config.has_or_not_generate_timeout,
    )


class QuestionStore:
    """待玩题目与近期出题记录的本地缓存。"""

    def __init__(
        self,
        path: Path,
        *,
        generate_count: Optional[int] = None,
        low_water: Optional[int] = None,
        history_size: Optional[int] = None,
    ) -> None:
        self.path = path
        self.generate_count = generate_count or config.has_or_not_generate_count
        self.low_water = low_water if low_water is not None else config.has_or_not_cache_low_water
        self.history_size = history_size or config.has_or_not_history_size
        self.questions: list[GeneratedQuestion] = []
        self.recent_answers: list[str] = []
        self.recent_word_sets: list[list[str]] = []
        self._loaded = False
        self._lock = asyncio.Lock()
        # 生成是慢操作（一次 20 题），用单独的一把锁保证同一进程内只生成一批
        self._generation_lock = asyncio.Lock()
        self._prefetch_task: Optional[asyncio.Task[None]] = None

    async def _load_locked(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            async with aiofiles.open(self.path, encoding="utf-8") as file:
                data = QuestionStoreData.model_validate_json(await file.read())
        except Exception:
            logger.opt(exception=True).warning(f"读取有无有无题目缓存失败: {self.path}")
            return
        self.questions = [question for question in data.questions if is_valid_question(question)]
        self.recent_answers = list(data.recent_answers)
        self.recent_word_sets = [list(word_set) for word_set in data.recent_word_sets]

    async def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = QuestionStoreData(
            questions=self.questions,
            recent_answers=self.recent_answers,
            recent_word_sets=self.recent_word_sets,
        )
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        async with aiofiles.open(temporary, "w", encoding="utf-8") as file:
            await file.write(data.model_dump_json(indent=2))
        temporary.replace(self.path)

    async def count(self) -> int:
        async with self._lock:
            await self._load_locked()
            return len(self.questions)

    async def pop(self) -> Optional[GeneratedQuestion]:
        """取出一道题并从缓存中删除；没有题目时返回 None。"""
        async with self._lock:
            await self._load_locked()
            if not self.questions:
                return None
            question = self.questions.pop(0)
            await self._save_locked()
            return question

    async def extend(self, candidates: list[GeneratedQuestion]) -> int:
        """过滤重复后写入缓存，返回实际写入的题目数。"""
        async with self._lock:
            await self._load_locked()
            accepted = filter_questions(candidates, self.recent_answers, self.recent_word_sets)
            if not accepted:
                return 0
            self.questions.extend(accepted)
            for question in accepted:
                self.recent_answers.append(normalize_answer(question.answer))
                self.recent_word_sets.append(list(question_word_signature(question)))
            self.recent_answers = self.recent_answers[-self.history_size :]
            self.recent_word_sets = self.recent_word_sets[-self.history_size :]
            await self._save_locked()
            return len(accepted)

    async def _history_snapshot(self) -> tuple[list[str], list[list[str]]]:
        async with self._lock:
            await self._load_locked()
            return list(self.recent_answers), [list(word_set) for word_set in self.recent_word_sets]

    async def _fill_locked(self) -> int:
        """调用方需持有 ``_generation_lock``：生成并写入一批题目。"""
        exclusions, word_sets = await self._history_snapshot()
        last_error: Optional[Exception] = None
        for _ in range(2):
            try:
                candidates = await generate_questions(exclusions, word_sets, self.generate_count)
            except Exception as error:
                last_error = error
                logger.opt(exception=True).warning("有无有无生成题目失败")
                continue
            added = await self.extend(candidates)
            if added:
                logger.info(f"有无有无：生成并缓存 {added} 道新题目")
                return added
        raise QuestionGenerationError("没有生成出不重复的题目") from last_error

    async def ensure_ready(self) -> None:
        """缓存为空时同步生成一批题目（首局开始时调用）。"""
        if await self.count() > 0:
            return
        async with self._generation_lock:
            if await self.count() > 0:
                return
            await self._fill_locked()

    async def fill(self) -> int:
        """无论缓存是否为空都补充一批题目（后台预生成用）。"""
        async with self._generation_lock:
            return await self._fill_locked()

    def schedule_prefetch(self) -> None:
        """题目数量低于低水位时在后台补充，不阻塞当前游戏。"""
        if self._prefetch_task is not None and not self._prefetch_task.done():
            return
        self._prefetch_task = asyncio.create_task(self._prefetch())

    async def _prefetch(self) -> None:
        try:
            if await self.count() >= self.low_water:
                return
            async with self._generation_lock:
                if await self.count() >= self.low_water:
                    return
                await self._fill_locked()
        except Exception:
            logger.opt(exception=True).warning("有无有无后台预生成题目失败")


_store: Optional[QuestionStore] = None


def get_question_store() -> QuestionStore:
    """进程内共享的题目缓存（LocalStore 数据目录）。"""
    global _store
    if _store is None:
        _store = QuestionStore(get_data_file("nonebot_plugin_has_or_not", "questions.json"))
    return _store
