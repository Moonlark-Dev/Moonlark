"""答案判定：先做本地精确匹配，再把题目、玩法规则与参考答案一并交给 ``nonebot_plugin_decision`` 判定。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nonebot import logger
from nonebot_plugin_decision import DecisionNotConfiguredError, NoulAnswer, ask, noul

from .config import config
from .lang import lang
from .store import is_exact_match

if TYPE_CHECKING:
    from .types import GeneratedQuestion

_JUDGE_IDENTIFY = "Has Or Not (Judge)"


def build_judge_state(question: GeneratedQuestion, guess: str, rules: str) -> dict[str, object]:
    """构造提交给 Decisions API 的判题上下文（玩法规则、题目词组、参考答案与玩家作答）。"""
    return {
        "rules": rules,
        "question": {
            "contains": [pair.contain.strip() for pair in question.prompts],
            "missing": [pair.missing.strip() for pair in question.prompts],
            "pairs": [{"contain": pair.contain.strip(), "missing": pair.missing.strip()} for pair in question.prompts],
        },
        "reference_answer": question.answer.strip(),
        "guess": guess,
    }


async def judge_guess(guess: str, question: GeneratedQuestion, user_id: str) -> bool:
    """判断玩家答案是否符合本题规则。

    本地精确匹配（大小写 / 全半角 / 空白不敏感）命中参考答案时直接通过；若直接照搬
    题面上的词语则直接拒绝；否则把「有无有无」的玩法规则、本题三组 ⭕/❌ 词语、
    参考答案与玩家作答一并交给 Decisions API，结合题目语境判断玩家表述是否与参考答案
    本质相同或同样满足规则（例如参考答案为“会发光”时接受“光”“发光”“光源”，但拒绝
    “用电”；参考答案为“圆形”时接受“圆”“o”“⭕”，但拒绝“球”）。

    未配置 Decisions API 时退化为精确匹配，不影响游戏进行。
    """
    guess = guess.strip()
    if not guess:
        return False
    answer = question.answer.strip()
    if is_exact_match(guess, answer):
        return True
    if any(is_exact_match(guess, word) for pair in question.prompts for word in (pair.contain, pair.missing)):
        return False
    rules = await lang.text("judge.rules", user_id)
    instructions = await lang.text("judge.instructions", user_id)
    true_text = await lang.text("judge.true", user_id)
    false_text = await lang.text("judge.false", user_id)
    state = build_judge_state(question, guess, rules)
    try:
        answers = await ask(
            state,
            {"correct": noul(instructions, true=true_text, false=false_text)},
            identify=_JUDGE_IDENTIFY,
        )
    except DecisionNotConfiguredError:
        logger.debug("有无有无：未配置 Decisions API，仅使用精确匹配判定答案")
        return False
    except Exception:
        logger.opt(exception=True).warning("有无有无：Decisions API 判定答案失败，按错误处理")
        return False
    result = answers.get("correct")
    if not isinstance(result, NoulAnswer):
        logger.warning(f"有无有无：Decisions API 没有返回有效判定（{guess!r} / {answer!r}）")
        return False
    probability = result.noul
    logger.info(f"有无有无：判定 {guess!r}（参考答案 {answer!r}）正确概率 {probability:.2f}")
    return probability >= config.has_or_not_judge_threshold
