"""题目生成、拆解核验、本地缓存与去重。"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import TYPE_CHECKING, Optional

import aiofiles
from nonebot import logger
from nonebot_plugin_larkutils import escape_markdown
from nonebot_plugin_localstore import get_data_file
from nonebot_plugin_openai import fetch_json, generate_message
from nonebot_plugin_openai.utils.message import get_message

from .config import config
from .types import GeneratedQuestion, QuestionStoreData

if TYPE_CHECKING:
    from pathlib import Path

_GENERATION_IDENTIFY = "Missing Abbreviations (Generate)"
_MAX_PROMPT_EXCLUSIONS = 40
_ABBREV_PUNCT_RE = re.compile(r"[.\-&/'·’]")


def normalize_answer(value: str) -> str:
    """归一化文本（NFKC、去首尾空白、转小写、去除所有空白字符，保留标点符号）。"""
    text = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"\s+", "", text)


def is_exact_match(guess: str, answer: str) -> bool:
    """大小写、全半角与空白不敏感的精确匹配（保留标点符号）。"""
    return normalize_answer(guess) == normalize_answer(answer)


_BUILTIN_EXCLUDED_ANSWERS: frozenset[str] = frozenset(
    normalize_answer(item)
    for item in (
        "奥运会",
        "高考",
        "德州",
        "然并卵",
        "zn",
        "si",
        "sry",
        "etc.",
        "etc",
        "i.e.",
        "ie",
        "麻酱",
        "麻油",
        "kksk",
        "u1s1",
    )
)

_BUILTIN_EXCLUDED_FULL_WORDS: frozenset[str] = frozenset(
    normalize_answer(item)
    for item in (
        "奥林匹克运动会",
        "普通高等学校招生全国统一考试",
        "德克萨斯州",
        "得克萨斯州",
        "然而并没有什么卵用",
        "zinc",
        "silicon",
        "sorry",
        "etcetera",
        "id est",
        "芝麻酱",
        "芝麻油",
        "ここ好き",
        "kokosuki",
        "有一说一",
        "you1yi1shuo1yi1",
        "youyishuoyi",
    )
)


class QuestionGenerationError(RuntimeError):
    """模型没有给出任何合法且不重复的题目。"""


def _identity(value: str) -> str:
    return value


def _has_line_break(value: str) -> bool:
    return "\n" in value or "\r" in value


def _strip_abbrev_punct(value: str) -> str:
    return _ABBREV_PUNCT_RE.sub("", normalize_answer(value))


def parse_breakdown(breakdown: str) -> Optional[tuple[str, str, str, str]]:
    """解析带 ``[ ]`` 的原词拆解式。

    拒绝空括号 ``[]``、嵌套 ``[``、未闭合/未匹配的括号，以及没有任何括号提取字符的情况。
    返回 ``(joined_text, bracketed_text, unbracketed_text, skeleton_mask)``。
    """
    joined_chars: list[str] = []
    bracketed_chars: list[str] = []
    unbracketed_chars: list[str] = []
    mask_chars: list[str] = []

    in_bracket = False
    current_segment: list[str] = []

    for ch in breakdown:
        if ch == "[":
            if in_bracket:
                return None
            in_bracket = True
            current_segment = []
        elif ch == "]":
            if not in_bracket:
                return None
            if not current_segment or not "".join(current_segment).strip():
                return None
            for seg_ch in current_segment:
                joined_chars.append(seg_ch)
                if seg_ch.isspace():
                    mask_chars.append(seg_ch)
                else:
                    bracketed_chars.append(seg_ch)
                    mask_chars.append("○")
            in_bracket = False
            current_segment = []
        elif in_bracket:
            current_segment.append(ch)
        else:
            joined_chars.append(ch)
            unbracketed_chars.append(ch)
            mask_chars.append(ch)

    if in_bracket or not bracketed_chars:
        return None

    return (
        "".join(joined_chars),
        "".join(bracketed_chars),
        "".join(unbracketed_chars),
        "".join(mask_chars),
    )


def _has_any_line_break(question: GeneratedQuestion) -> bool:
    texts = [
        question.full_word,
        question.breakdown,
        question.question,
        *question.answers,
        *question.hint,
        *question.tags.keys(),
        *question.tags.values(),
    ]
    return any(_has_line_break(item) for item in texts)


def _has_valid_hints(question: GeneratedQuestion, skeleton_mask: str) -> bool:
    if not (1 <= len(question.hint) <= 2):
        return False
    if any(not normalize_answer(item) for item in question.hint):
        return False
    if normalize_answer(question.hint[0]) != normalize_answer(skeleton_mask):
        return False
    if len(question.hint) == 2:
        second_hint = question.hint[1]
        if is_exact_match(second_hint, question.full_word) or any(
            is_exact_match(second_hint, ans) for ans in question.answers
        ):
            return False
    return True


def _is_distinct_abbreviated_pair(question: GeneratedQuestion, joined_text: str) -> bool:
    if is_exact_match(question.question, question.full_word) or is_exact_match(question.question, joined_text):
        return False
    return not any(
        is_exact_match(ans, question.question)
        or is_exact_match(ans, question.full_word)
        or is_exact_match(ans, joined_text)
        for ans in question.answers
    )


def is_valid_question(question: GeneratedQuestion) -> bool:
    """纯函数校验题目是否满足《缩略》的字符拆解恒等式与结构约束（不修改入参）。"""
    if _has_any_line_break(question) or not (1 <= question.difficulty <= 5):
        return False

    full_word_norm = normalize_answer(question.full_word)
    question_norm = normalize_answer(question.question)
    if (
        not full_word_norm
        or not _strip_abbrev_punct(question.question)
        or not question.answers
        or any(not normalize_answer(ans) for ans in question.answers)
    ):
        return False

    parsed = parse_breakdown(question.breakdown)
    if parsed is None:
        return False
    joined_text, bracketed_text, unbracketed_text, skeleton_mask = parsed

    bracketed_alpha = _strip_abbrev_punct(bracketed_text)
    if (
        normalize_answer(unbracketed_text) != question_norm
        or not bracketed_alpha
        or bracketed_alpha != _strip_abbrev_punct(question.answers[0])
    ):
        return False

    if "变格" not in question.tags and normalize_answer(joined_text) != full_word_norm:
        return False

    return _has_valid_hints(question, skeleton_mask) and _is_distinct_abbreviated_pair(question, joined_text)


def filter_questions(
    candidates: list[GeneratedQuestion],
    known_full_words: list[str],
    known_answers: list[str],
    known_questions: list[str],
) -> list[GeneratedQuestion]:
    """过滤结构不合法、命中内置例题黑名单，或与近期/同批题目重复的题目。"""
    seen_full_words: set[str] = {
        normalize_answer(word) for word in known_full_words if word
    } | _BUILTIN_EXCLUDED_FULL_WORDS
    seen_answers: set[str] = {normalize_answer(ans) for ans in known_answers if ans} | _BUILTIN_EXCLUDED_ANSWERS
    seen_questions: set[str] = {normalize_answer(q) for q in known_questions if q}

    accepted: list[GeneratedQuestion] = []
    for candidate in candidates:
        if not is_valid_question(candidate):
            continue
        parsed = parse_breakdown(candidate.breakdown)
        if parsed is None:
            continue

        full_norm = normalize_answer(candidate.full_word)
        joined_norm = normalize_answer(parsed[0])
        q_norm = normalize_answer(candidate.question)
        ans_norms = [normalize_answer(ans) for ans in candidate.answers]

        if (
            full_norm in seen_full_words
            or joined_norm in seen_full_words
            or q_norm in seen_questions
            or any(ans_norm in seen_answers for ans_norm in ans_norms)
        ):
            continue

        seen_full_words.add(full_norm)
        seen_full_words.add(joined_norm)
        seen_questions.add(q_norm)
        seen_answers.update(ans_norms)
        accepted.append(candidate)

    return accepted


def format_difficulty(difficulty: int) -> str:
    """将难度整数（夹逼至 1..5）格式化为星级字符串。"""
    clamped = min(max(difficulty, 1), 5)
    return f"{'★' * clamped}{'☆' * (5 - clamped)} ({clamped}/5)"


def format_question(
    question: GeneratedQuestion,
    revealed_hints: int = 0,
    escape: bool = False,
) -> str:
    """按通用多行纯文本格式渲染题目（用于纯文本回退）。"""
    escaper = escape_markdown if escape else _identity
    q_text = escaper(question.question.strip())
    stars = format_difficulty(question.difficulty)
    lines = [
        "【缩略】",
        f"题面：{q_text}",
        f"难度：{stars}",
    ]
    if question.tags:
        tag_items: list[str] = []
        for name, desc in question.tags.items():
            tag_name = escaper(name.strip())
            tag_desc = escaper(desc.strip())
            tag_items.append(f"【{tag_name}】{tag_desc}" if tag_desc else f"【{tag_name}】")
        lines.append("标签：" + "；".join(tag_items))

    shown = min(max(revealed_hints, 0), len(question.hint))
    if shown > 0:
        for idx, hint_text in enumerate(question.hint[:shown], start=1):
            lines.append(f"💡 提示 {idx}：{escaper(hint_text.strip())}")
    else:
        lines.append(f"可用提示：{len(question.hint)} 条（免费）")
    return "\n".join(lines)


def format_question_markdown(
    question: GeneratedQuestion,
    revealed_hints: int = 0,
    escape: bool = True,
) -> str:
    """按 Markdown 表格与段落样式渲染题目（用于 QQ 官方消息与非 QQ 平台图片渲染，严禁输出裸 ``<`` 或 ``>``）。"""
    escaper = escape_markdown if escape else _identity
    q_text = escaper(question.question.strip())
    stars = format_difficulty(question.difficulty)
    lines = [
        "### 缩略",
        "",
        "| 题面 | 难度 |",
        "| :--- | :--- |",
        f"| **{q_text}** | {stars} |",
        "",
    ]
    if question.tags:
        for name, desc in question.tags.items():
            tag_name = escaper(name.strip())
            tag_desc = escaper(desc.strip())
            if tag_desc:
                lines.append(f"- **【{tag_name}】**：{tag_desc}")
            else:
                lines.append(f"- **【{tag_name}】**")
        lines.append("")

    shown = min(max(revealed_hints, 0), len(question.hint))
    if shown > 0:
        for idx, hint_text in enumerate(question.hint[:shown], start=1):
            lines.extend((f"**💡 提示 {idx}**：{escaper(hint_text.strip())}", ""))
    else:
        lines.extend((f"**💡 可用提示**：{len(question.hint)} 条（免费）", ""))

    lines.append("请还原原词，作答被抽走的「缩略词」（提示免费不扣次数）")
    return "\n".join(lines)


def format_answer_summary(question: GeneratedQuestion) -> tuple[str, str]:
    """返回 ``(answers_display, origin_display)`` 用于结算揭晓答案与原词拆解。"""
    distinct_answers = list(dict.fromkeys(ans.strip() for ans in question.answers if ans.strip()))
    answers_display = " / ".join(distinct_answers)

    breakdown = question.breakdown.strip()
    full_word = question.full_word.strip()
    parsed = parse_breakdown(breakdown)
    if parsed is not None and normalize_answer(parsed[0]) == normalize_answer(full_word):
        origin_display = breakdown
    else:
        origin_display = f"{full_word} → {breakdown}" if full_word and breakdown else (full_word or breakdown)
    return answers_display, origin_display


def build_generation_extra(
    excluded_full_words: list[str],
    excluded_answers: list[str],
    count: int,
) -> str:
    """构造追加在系统提示词之后的 user 消息，附带近期去重列表与题量约束。"""
    lines = [
        "请再额外遵守以下要求：",
        (
            f"1. 请一次性生成 {count} 道《缩略》题目，放入同一个 JSON 数组中；"
            "严格核对每道题的 breakdown 括号恒等式，不要输出任何额外文字，不要使用 Markdown 代码块。"
        ),
    ]
    recent_words = [word for word in excluded_full_words[-_MAX_PROMPT_EXCLUSIONS:] if word]
    if recent_words:
        lines.append("2. 以下原词近期已经出过，请勿重复使用：" + "、".join(recent_words))
    recent_ans = [ans for ans in excluded_answers[-_MAX_PROMPT_EXCLUSIONS:] if ans]
    if recent_ans:
        lines.append("3. 以下缩略词答案近期已经出过，请勿重复使用：" + "、".join(recent_ans))
    return "\n".join(lines)


def _ensure_dotless_answer_alias(question: GeneratedQuestion) -> GeneratedQuestion:
    """若模型输出的带缩写点答案（如 ``e.g.``）漏写了无点形式且原词拆解本身不含点，自动补齐无点写法。"""
    parsed = parse_breakdown(question.breakdown)
    if parsed is None or "." in parsed[1]:
        return question
    extra_aliases: list[str] = []
    existing_norms = {normalize_answer(ans) for ans in question.answers}
    for ans in question.answers:
        if "." in ans:
            dotless = ans.replace(".", "").strip()
            dotless_norm = normalize_answer(dotless)
            if dotless_norm and dotless_norm not in existing_norms:
                existing_norms.add(dotless_norm)
                extra_aliases.append(dotless)
    if not extra_aliases:
        return question
    return question.model_copy(update={"answers": [*question.answers, *extra_aliases]})


async def generate_questions(
    excluded_full_words: list[str],
    excluded_answers: list[str],
    count: int,
) -> list[GeneratedQuestion]:
    """调用 OpenAI 插件批量生成《缩略》题目（模型由 ``/model`` 按应用标识配置）。"""
    messages = [
        await get_message("system", "missing_abbreviations/system.md.jinja"),
        generate_message(build_generation_extra(excluded_full_words, excluded_answers, count), "user"),
    ]
    generated = await fetch_json(
        messages,
        list[GeneratedQuestion],
        identify=_GENERATION_IDENTIFY,
        timeout=config.missing_abbreviations_generate_timeout,
    )
    return [_ensure_dotless_answer_alias(item) for item in generated]


def _trim_history(items: list[str], limit: int) -> list[str]:
    return items[-limit:] if limit > 0 else []


class QuestionStore:
    """待玩题目与近期出题去重记录的本地缓存。"""

    def __init__(
        self,
        path: Path,
        *,
        generate_count: Optional[int] = None,
        low_water: Optional[int] = None,
        history_size: Optional[int] = None,
    ) -> None:
        self.path = path
        self.generate_count = (
            generate_count if generate_count is not None else config.missing_abbreviations_generate_count
        )
        self.low_water = low_water if low_water is not None else config.missing_abbreviations_cache_low_water
        self.history_size = history_size if history_size is not None else config.missing_abbreviations_history_size
        self.questions: list[GeneratedQuestion] = []
        self.recent_full_words: list[str] = []
        self.recent_answers: list[str] = []
        self.recent_questions: list[str] = []
        self._loaded = False
        self._lock = asyncio.Lock()
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
            logger.opt(exception=True).warning(f"读取缩略题目缓存失败: {self.path}")
            return
        self.questions = [question for question in data.questions if is_valid_question(question)]
        self.recent_full_words = list(data.recent_full_words)
        self.recent_answers = list(data.recent_answers)
        self.recent_questions = list(data.recent_questions)

    async def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = QuestionStoreData(
            questions=self.questions,
            recent_full_words=self.recent_full_words,
            recent_answers=self.recent_answers,
            recent_questions=self.recent_questions,
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
        """取出一道题并从缓存中移除；缓存为空时返回 None。"""
        async with self._lock:
            await self._load_locked()
            if not self.questions:
                return None
            question = self.questions.pop(0)
            await self._save_locked()
            return question

    async def extend(self, candidates: list[GeneratedQuestion]) -> int:
        """过滤不合法与重复题目后写入缓存，返回实际新增题目数量。"""
        async with self._lock:
            await self._load_locked()
            accepted = filter_questions(
                candidates,
                self.recent_full_words,
                self.recent_answers,
                self.recent_questions,
            )
            if not accepted:
                return 0
            self.questions.extend(accepted)
            for question in accepted:
                full_norm = normalize_answer(question.full_word)
                self.recent_full_words.append(full_norm)
                parsed = parse_breakdown(question.breakdown)
                if parsed is not None:
                    joined_norm = normalize_answer(parsed[0])
                    if joined_norm != full_norm:
                        self.recent_full_words.append(joined_norm)
                for ans in question.answers:
                    ans_norm = normalize_answer(ans)
                    if ans_norm:
                        self.recent_answers.append(ans_norm)
                self.recent_questions.append(normalize_answer(question.question))

            self.recent_full_words = _trim_history(self.recent_full_words, self.history_size)
            self.recent_answers = _trim_history(self.recent_answers, self.history_size)
            self.recent_questions = _trim_history(self.recent_questions, self.history_size)
            await self._save_locked()
            return len(accepted)

    async def _history_snapshot(self) -> tuple[list[str], list[str]]:
        async with self._lock:
            await self._load_locked()
            return list(self.recent_full_words), list(self.recent_answers)

    async def _fill_locked(self) -> int:
        """调用方需持有 ``_generation_lock``：生成并写入一批新题目。"""
        excluded_full_words, excluded_answers = await self._history_snapshot()
        last_error: Optional[Exception] = None
        for _ in range(2):
            try:
                candidates = await generate_questions(
                    excluded_full_words,
                    excluded_answers,
                    self.generate_count,
                )
            except Exception as error:
                last_error = error
                logger.opt(exception=True).warning("缩略生成题目失败")
                continue
            added = await self.extend(candidates)
            if added:
                logger.info(f"缩略：生成并缓存 {added} 道新题目")
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
        """题目数量低于低水位时在后台异步补充，不阻塞当前游戏。"""
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
            logger.opt(exception=True).warning("缩略后台预生成题目失败")


_store: Optional[QuestionStore] = None


def get_question_store() -> QuestionStore:
    """获取进程内共享的《缩略》题目缓存（LocalStore 数据目录）。"""
    global _store
    if _store is None:
        _store = QuestionStore(get_data_file("nonebot_plugin_missing_abbreviations", "questions.json"))
    return _store
