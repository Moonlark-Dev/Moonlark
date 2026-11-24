"""海龟汤的 VimCoin 收支：开局与提示扣费、答对奖励的发放。

所有金额都来自 :mod:`nonebot_plugin_turtle_soup.config`，费用配置为 0 时对应操作
直接跳过，便于关闭某一项收费。扣费失败（余额不足）抛 :class:`InsufficientVimcoinError`，
由指令层换成一条提示；退款与奖励属于「已经收下的钱 / 已经打出的奖励」，失败只记日志，
不能影响本局的结算与消息发送。
"""

from __future__ import annotations

from nonebot import logger
from nonebot_plugin_larkuser import get_user


class InsufficientVimcoinError(RuntimeError):
    """余额不足以支付本局费用。"""

    def __init__(self, cost: float, balance: float) -> None:
        super().__init__(f"VimCoin 不足：需要 {format_vimcoin(cost)} vi，当前只有 {format_vimcoin(balance)} vi")
        self.cost = cost
        self.balance = balance


def format_vimcoin(value: float) -> str:
    """VimCoin 展示：整数去掉小数点，其他保留两位。"""
    value = float(value)
    return str(int(value)) if value.is_integer() else str(round(value, 2))


async def ensure_affordable(user_id: str, cost: float) -> None:
    """只检查余额、不扣费。

    开局前先用它拦下余额不足，避免先发出「正在生成」再告诉玩家付不起。
    """
    if cost <= 0:
        return
    user = await get_user(user_id)
    if not await user.has_vimcoin(cost):
        raise InsufficientVimcoinError(cost, user.get_vimcoin())


async def charge(user_id: str, cost: float) -> None:
    """扣除费用；余额不足时抛 :class:`InsufficientVimcoinError`，不会产生半笔扣费。"""
    if cost <= 0:
        return
    user = await get_user(user_id)
    if not await user.use_vimcoin(cost):
        raise InsufficientVimcoinError(cost, user.get_vimcoin())


async def refund(user_id: str, cost: float, reason: str) -> None:
    """退还费用；退还失败只记日志，不影响调用方继续处理。"""
    if cost <= 0:
        return
    try:
        user = await get_user(user_id)
        await user.add_vimcoin(cost)
    except Exception:
        logger.opt(exception=True).error(
            f"海龟汤：向 {user_id} 退还 {format_vimcoin(cost)} vi 失败（{reason}）",
        )


async def reward(user_id: str, amount: float) -> float:
    """发放奖励，返回实际发放的数量（发放失败时为 0）。"""
    if amount <= 0:
        return 0.0
    try:
        user = await get_user(user_id)
        await user.add_vimcoin(amount)
    except Exception:
        logger.opt(exception=True).error(f"海龟汤：向 {user_id} 发放 {format_vimcoin(amount)} vi 奖励失败")
        return 0.0
    return amount
