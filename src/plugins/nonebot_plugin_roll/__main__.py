from random import randint

from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_larkuser import MoonlarkUser, get_user, patch_matcher
from nonebot_plugin_larkutils import get_user_id

from .lang import lang

MAX_COUNT = 100

alc = Alconna("roll", Args["count?", int, 1])
roll = on_alconna(alc)
patch_matcher(roll)


def get_dice_value() -> int:
    """掷一个加权二十面骰子，返回点数（1-20）"""
    c = randint(0, 200)  # nosec B311
    if 193 <= c <= 200:  # 20
        return 20
    if 183 <= c <= 192:  # 18-19
        return randint(18, 19)  # nosec B311
    if 153 <= c <= 182:  # 15-17
        return randint(15, 17)  # nosec B311
    if 106 <= c <= 152:  # 10-14
        return randint(10, 14)  # nosec B311
    if 16 <= c <= 105:  # 2-9
        return randint(2, 9)  # nosec B311
    if c <= 15:  # 1
        return 1
    return 0


def get_vimcoin_delta(value: int) -> int:
    """根据骰子点数计算 vi 收益"""
    if value == 20:
        return 50
    if value in (18, 19):
        return 20
    if value in (15, 16, 17):
        return 10
    if value in (10, 11, 12, 13, 14):
        return 5
    if value == 1:
        return -50
    return 0


async def apply_reward(user: MoonlarkUser, delta: int) -> None:
    """为结算修正 vi 余额"""
    if delta > 0:
        await user.add_vimcoin(delta)
    elif delta < 0:
        await user.use_vimcoin(-delta, force=True)


async def get_delta_summary(user_id: str, delta: int) -> str:
    if delta > 0:
        return await lang.text("outcome.gain", user_id, delta)
    if delta < 0:
        return await lang.text("outcome.loss", user_id, -delta)
    return await lang.text("outcome.none", user_id)


@roll.handle()
async def _(user_id: str = get_user_id(), count: int = 1) -> None:
    if count <= 0:
        await lang.finish("invalid_count", user_id)
    if count > MAX_COUNT:
        await lang.finish("too_many", user_id, MAX_COUNT)

    user = await get_user(user_id)
    values = [get_dice_value() for _ in range(count)]
    delta = 0
    for value in values:
        single_delta = get_vimcoin_delta(value)
        await apply_reward(user, single_delta)
        delta += single_delta

    if count == 1:
        value = values[0]
        effects = []
        if value == 20:
            effects.append(await lang.text("effect.crit", user_id))
        elif value in (18, 19):
            effects.append(await lang.text("effect.success", user_id))
        elif value == 1:
            effects.append(await lang.text("effect.fail", user_id))
        effects.append(await get_delta_summary(user_id, delta))
        await lang.finish("result_single", user_id, value, "".join(effects))

    await lang.finish(
        "result_multi",
        user_id,
        count,
        "、".join(str(v) for v in values),
        sum(values),
        await get_delta_summary(user_id, delta),
    )
