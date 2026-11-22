"""谜题生成与问题判定。

判定默认走 ``nonebot_plugin_decision``（``TURTLE_SOUP_JUDGE_MODE=decision``）：
一次请求同时拿到「是 / 不是 / 不重要」三选一、是否已经说出汤底、以及 0~10 的进度等级。
出现以下情况时退回 ``nonebot_plugin_openai`` 的 LLM 判定：

- 环境变量把 ``TURTLE_SOUP_JUDGE_MODE`` 设为 ``llm``；
- 没有配置 ``DECISION_API_KEY``；
- Decisions API 请求失败或返回了无法解析的答案；
- 判定的置信度低于 ``TURTLE_SOUP_DECISION_MIN_CONFIDENCE``（默认 0.5）。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from nonebot import logger
from nonebot_plugin_decision import (
    ChoiceAnswer,
    DecisionNotConfiguredError,
    NoulAnswer,
    ScoreAnswer,
    ask,
    choice,
    noul,
    score,
)
from nonebot_plugin_decision.config import config as decision_config
from nonebot_plugin_openai import fetch_json, generate_message
from nonebot_plugin_openai.utils.message import get_message

from .config import config
from .lang import lang
from .types import (
    HistoryItem,
    JudgeResult,
    LLMJudgeResponse,
    ProgressResponse,
    Puzzle,
)

GENERATE_IDENTIFY = "Turtle Soup (Generate)"
JUDGE_IDENTIFY = "Turtle Soup (Judge)"
RECALCULATE_IDENTIFY = "Turtle Soup (Recalculate)"

# 三选一的选项键必须是 OpenRouter 允许的 ASCII 键
ANSWER_KEYS = ("yes", "no", "irrelevant")
_LEGAL_REPLY_KEYS = {
    "是": "reply.yes",
    "是的": "reply.yes",
    "yes": "reply.yes",
    "不是": "reply.no",
    "否": "reply.no",
    "no": "reply.no",
    "不重要": "reply.irrelevant",
    "irrelevant": "reply.irrelevant",
}
# 进度等级数（0~10）
PROGRESS_LEVELS = 11


class JudgeError(RuntimeError):
    """判定失败（decision 与 LLM 两条路都没能给出结果）。"""


def _build_state(
    puzzle: Puzzle,
    history: list[HistoryItem],
    percent: int,
    question: str = "",
) -> dict[str, object]:
    """构造提交给判定模型的上下文（与上游插件的键名保持一致）。"""
    state: dict[str, object] = {
        "puzzle_setting": puzzle.puzzle_setting,
        "supplementary_info": puzzle.supplementary_info,
        "solution": puzzle.solution,
        "history": [{"question": item.question, "reply": item.reply, "percent": item.percent} for item in history],
        "last_percentage": percent,
    }
    if question:
        state["player_question"] = question
    return state


def _clamp_percent(value: int, current: int, *, solved: bool) -> int:
    """进度只允许增加；未解开时最高 99，解开时固定 100。"""
    if solved:
        return 100
    return max(current, max(0, min(99, int(value))))


def _score_to_percent(answer: ScoreAnswer) -> int:
    """把 Decisions API 的 score 换算成百分比。

    正常情况下 score 是 0~10 的等级下标（等级描述见语言文件）；
    个别模型会直接返回 0~100 的百分比（用明显大于等级数的 20 作为分界），
    这里一并接受，避免把 70 当成第 10 档。
    """
    raw = float(answer.score)
    if raw > 20:
        return max(0, min(100, round(raw)))
    level = max(0, min(PROGRESS_LEVELS - 1, round(raw)))
    return round(level * 100 / (PROGRESS_LEVELS - 1))


def _confidence(answer: Any) -> Optional[float]:
    """读取答案里的 confidence；模型没有返回该字段时视为「可信」（返回 None）。

    Pydantic 的默认值是 0.0，直接比较会把「没有 confidence」误判成「置信度为 0」，
    导致每次判定都退回 LLM。
    """
    if "confidence" not in getattr(answer, "model_fields_set", set()):
        return None
    value = getattr(answer, "confidence", None)
    return float(value) if value is not None else None


# 用户 ID -> 判定用到的本地化文本；语言切换不频繁，缓存避免每次提问查十几次语言表
_decision_text_cache: dict[str, dict[str, Any]] = {}
_DECISION_TEXT_CACHE_SIZE = 64


async def _decision_texts(user_id: str) -> dict[str, Any]:
    cached = _decision_text_cache.get(user_id)
    if cached is not None:
        return cached
    texts: dict[str, Any] = {
        "answer_instructions": await lang.text("judge.decision.answer_instructions", user_id),
        "answer_yes": await lang.text("judge.decision.answer_yes", user_id),
        "answer_no": await lang.text("judge.decision.answer_no", user_id),
        "answer_irrelevant": await lang.text("judge.decision.answer_irrelevant", user_id),
        "solved_instructions": await lang.text("judge.decision.solved_instructions", user_id),
        "solved_true": await lang.text("judge.decision.solved_true", user_id),
        "solved_false": await lang.text("judge.decision.solved_false", user_id),
        "progress_instructions": await lang.text("judge.decision.progress_instructions", user_id),
        "levels": [
            await lang.text(f"judge.decision.progress_level_{level}", user_id) for level in range(PROGRESS_LEVELS)
        ],
    }
    if len(_decision_text_cache) >= _DECISION_TEXT_CACHE_SIZE:
        _decision_text_cache.clear()
    _decision_text_cache[user_id] = texts
    return texts


async def generate_puzzle(theme: str) -> Puzzle:
    """调用模型生成一道新谜题。"""
    theme_text = f"\n用户期望的谜题主题为：{theme.strip()}" if theme.strip() else ""
    messages = [
        await get_message("system", "turtle_soup/generate.md.jinja"),
        generate_message(
            "### **执行指令**\n\n"
            "现在，启动你的内容生成引擎。请遵循以上所有规则，为我生成 **1** 个全新的、"
            f"符合 JSON 格式的海龟汤谜题。将它们包含在一个 JSON 数组中。{theme_text}",
            "user",
        ),
    ]
    puzzles = await fetch_json(
        messages,
        list[Puzzle],
        identify=GENERATE_IDENTIFY,
        timeout=config.turtle_soup_generate_timeout,
        temperature=0.9,
    )
    if not puzzles:
        raise JudgeError("模型没有返回任何谜题")
    return puzzles[0]


async def _judge_with_decision(
    puzzle: Puzzle,
    history: list[HistoryItem],
    percent: int,
    question: str,
    user_id: str,
    session_id: str,
) -> Optional[JudgeResult]:
    """Decisions API 判定；无法给出可信结果时返回 None，交由 LLM 判定。"""
    texts = await _decision_texts(user_id)
    answers = await ask(
        _build_state(puzzle, history, percent, question),
        {
            "answer": choice(
                texts["answer_instructions"],
                criteria={
                    "yes": texts["answer_yes"],
                    "no": texts["answer_no"],
                    "irrelevant": texts["answer_irrelevant"],
                },
            ),
            "solved": noul(
                texts["solved_instructions"],
                true=texts["solved_true"],
                false=texts["solved_false"],
            ),
            "progress": score(texts["progress_instructions"], criteria=texts["levels"]),
        },
        identify=JUDGE_IDENTIFY,
        request_timeout=config.turtle_soup_decision_timeout,
        session_id=session_id,
    )

    answer = answers.get("answer")
    if not isinstance(answer, ChoiceAnswer) or answer.choice not in ANSWER_KEYS:
        logger.warning(f"海龟汤：Decisions API 没有给出有效的三选一答案（{answer!r}），改用 LLM 判定")
        return None
    answer_confidence = _confidence(answer)
    if answer_confidence is not None and answer_confidence < config.turtle_soup_decision_min_confidence:
        logger.info(
            f"海龟汤：Decisions API 判定置信度 {answer_confidence:.2f} 低于 "
            f"{config.turtle_soup_decision_min_confidence:.2f}，改用 LLM 判定",
        )
        return None

    solved_answer = answers.get("solved")
    solved = isinstance(solved_answer, NoulAnswer) and solved_answer.noul >= config.turtle_soup_solved_threshold
    solved_confidence = _confidence(solved_answer)
    if solved and solved_confidence is not None and solved_confidence < config.turtle_soup_decision_min_confidence:
        logger.info(f"海龟汤：是否解开的判定置信度 {solved_confidence:.2f} 过低，按未解开处理")
        solved = False

    progress_answer = answers.get("progress")
    new_percent = percent
    progress_confidence = _confidence(progress_answer)
    if isinstance(progress_answer, ScoreAnswer) and (
        progress_confidence is None or progress_confidence >= config.turtle_soup_decision_min_confidence
    ):
        new_percent = _clamp_percent(_score_to_percent(progress_answer), percent, solved=solved)
    if solved:
        new_percent = 100

    if solved:
        reply = await lang.text("reply.solved", user_id)
    else:
        reply = await lang.text(f"reply.{answer.choice}", user_id)
    return JudgeResult(reply=reply, percent=new_percent, solved=solved)


async def _judge_with_llm(
    puzzle: Puzzle,
    history: list[HistoryItem],
    percent: int,
    question: str,
    user_id: str,
) -> JudgeResult:
    """LLM 判定：返回 ``percent`` 与 ``reply`` 的 JSON。"""
    messages = [
        await get_message("system", "turtle_soup/judge.md.jinja"),
        generate_message(
            json.dumps(_build_state(puzzle, history, percent, question), ensure_ascii=False),
            "user",
        ),
    ]
    response = await fetch_json(
        messages,
        LLMJudgeResponse,
        identify=JUDGE_IDENTIFY,
        timeout=config.turtle_soup_judge_timeout,
        temperature=0.3,
    )
    solved = response.percent >= 100
    raw_reply = response.reply.strip()
    if solved:
        reply = raw_reply[:200] or await lang.text("reply.solved", user_id)
    else:
        # 未解开时只允许三个固定回答，避免模型给出解释而剧透
        key = _LEGAL_REPLY_KEYS.get(raw_reply)
        reply = await lang.text(key, user_id) if key else await lang.text("reply.irrelevant", user_id)
    return JudgeResult(reply=reply, percent=_clamp_percent(response.percent, percent, solved=solved), solved=solved)


def _decision_available() -> bool:
    """未配置 DECISION_API_KEY 时直接走 LLM，避免先做十几次语言查询再抛异常。"""
    return bool(decision_config.decision_api_key)


async def judge_question(
    puzzle: Puzzle,
    history: list[HistoryItem],
    percent: int,
    question: str,
    user_id: str,
    session_id: str,
) -> JudgeResult:
    """判定一次提问；decision 不可信时自动退回 LLM。"""
    if config.turtle_soup_judge_mode == "decision" and _decision_available():
        try:
            result = await _judge_with_decision(puzzle, history, percent, question, user_id, session_id)
        except DecisionNotConfiguredError:
            logger.info("海龟汤：未配置 DECISION_API_KEY，改用 LLM 判定")
        except Exception:
            logger.opt(exception=True).warning("海龟汤：Decisions API 判定失败，改用 LLM 判定")
        else:
            if result is not None:
                return result

    try:
        return await _judge_with_llm(puzzle, history, percent, question, user_id)
    except Exception as e:
        raise JudgeError(f"判定失败: {e}") from e


async def _recalculate_with_decision(
    puzzle: Puzzle,
    history: list[HistoryItem],
    percent: int,
    user_id: str,
    session_id: str,
) -> Optional[int]:
    """用 Decisions API 重算进度；不可信时返回 None。"""
    texts = await _decision_texts(user_id)
    answers = await ask(
        _build_state(puzzle, history, percent),
        {"progress": score(texts["progress_instructions"], criteria=texts["levels"])},
        identify=RECALCULATE_IDENTIFY,
        request_timeout=config.turtle_soup_decision_timeout,
        session_id=session_id,
    )
    progress_answer = answers.get("progress")
    if not isinstance(progress_answer, ScoreAnswer):
        logger.warning("海龟汤：Decisions API 没有给出有效的进度答案，改用 LLM 重算")
        return None
    progress_confidence = _confidence(progress_answer)
    if progress_confidence is not None and progress_confidence < config.turtle_soup_decision_min_confidence:
        logger.info(
            f"海龟汤：进度判定置信度 {progress_confidence:.2f} 低于 "
            f"{config.turtle_soup_decision_min_confidence:.2f}，改用 LLM 重算",
        )
        return None
    return _clamp_percent(_score_to_percent(progress_answer), percent, solved=False)


async def _recalculate_with_llm(
    puzzle: Puzzle,
    history: list[HistoryItem],
    percent: int,
) -> int:
    messages = [
        await get_message("system", "turtle_soup/progress.md.jinja"),
        generate_message(
            json.dumps(_build_state(puzzle, history, percent), ensure_ascii=False),
            "user",
        ),
    ]
    response = await fetch_json(
        messages,
        ProgressResponse,
        identify=RECALCULATE_IDENTIFY,
        timeout=config.turtle_soup_judge_timeout,
        temperature=0.3,
    )
    return _clamp_percent(response.recalculated_percent, percent, solved=False)


async def recalculate_progress(
    puzzle: Puzzle,
    history: list[HistoryItem],
    percent: int,
    user_id: str,
    session_id: str,
) -> int:
    """依据完整历史重算进度；decision 不可信时自动退回 LLM。"""
    if config.turtle_soup_judge_mode == "decision" and _decision_available():
        try:
            result = await _recalculate_with_decision(puzzle, history, percent, user_id, session_id)
        except DecisionNotConfiguredError:
            logger.info("海龟汤：未配置 DECISION_API_KEY，改用 LLM 重算进度")
        except Exception:
            logger.opt(exception=True).warning("海龟汤：Decisions API 重算进度失败，改用 LLM")
        else:
            if result is not None:
                return result

    try:
        return await _recalculate_with_llm(puzzle, history, percent)
    except Exception as e:
        raise JudgeError(f"重算进度失败: {e}") from e
