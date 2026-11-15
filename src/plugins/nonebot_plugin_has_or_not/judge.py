"""答案判定：先做本地精确匹配，再交给 ``nonebot_plugin_decision`` 判断语义是否相同。"""

from __future__ import annotations

from nonebot import logger
from nonebot_plugin_decision import DecisionNotConfiguredError, NoulAnswer, ask, noul

from .config import config
from .lang import lang
from .store import is_exact_match

_JUDGE_IDENTIFY = "Has Or Not (Judge)"


async def judge_guess(guess: str, answer: str, user_id: str) -> bool:
    """判断玩家答案是否正确。

    本地精确匹配（大小写 / 全半角 / 句读不敏感）命中时直接通过；否则交给
    Decisions API 判断“意思是否相同”，从而接受“圆形”与“圆”“o”“O”“⭕”这类
    同义或同形写法，但拒绝“球”这类相关却不同的词。

    未配置 Decisions API 时退化为精确匹配，不影响游戏进行。
    """
    guess = guess.strip()
    if not guess:
        return False
    if is_exact_match(guess, answer):
        return True
    instructions = await lang.text("judge.instructions", user_id)
    true_text = await lang.text("judge.true", user_id)
    false_text = await lang.text("judge.false", user_id)
    try:
        answers = await ask(
            {"answer": answer, "guess": guess},
            {"same": noul(instructions, true=true_text, false=false_text)},
            identify=_JUDGE_IDENTIFY,
        )
    except DecisionNotConfiguredError:
        logger.debug("有无有无：未配置 Decisions API，仅使用精确匹配判定答案")
        return False
    except Exception:
        logger.opt(exception=True).warning("有无有无：Decisions API 判定答案失败，按错误处理")
        return False
    result = answers.get("same")
    if not isinstance(result, NoulAnswer):
        logger.warning(f"有无有无：Decisions API 没有返回有效判定（{guess!r} / {answer!r}）")
        return False
    probability = result.noul
    logger.info(f"有无有无：判定 {guess!r} 与 {answer!r} 相同概率 {probability:.2f}")
    return probability >= config.has_or_not_judge_threshold
