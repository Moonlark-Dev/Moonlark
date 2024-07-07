from datetime import datetime
import json
import math
from typing import Literal
import aiofiles
from nonebot_plugin_alconna import Match
from nonebot_plugin_apscheduler import scheduler
from nonebot import get_driver, logger
from nonebot_plugin_localstore import get_data_file

from ...nonebot_plugin_larkuser.utils.vimcoin import add_vimcoin
from .count import add_exchanged_count
from .item import get_target_item

from ...nonebot_plugin_bag.exceptions import ItemLockedError
from ...nonebot_plugin_bag.utils.reduce import ALL, ItemNotEnough, remove_item_from_bag
from ...nonebot_plugin_items.items.moonlark.pawcoin import get_location
from ..lang import lang

from .vimcoin import get_total_vimcoin

from .count import get_exchanged_pawcoin

from ..config import config

path = get_data_file("nonebot_plugin_pawcoin_collecting", "exchange.json")


@get_driver().on_startup
async def _() -> None:
    if not path.exists():
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(
                json.dumps({"initial": config.pawcoin_default_exchange, "exchange": config.pawcoin_default_exchange})
            )


async def get_exchange_data(k: Literal["exchange", "initial"] = "exchange") -> float:
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        data = await f.read()
        return json.loads(data)[k]


async def calculate_exchange() -> float:
    a, b, c, d = config.pawcoin_exchange_vars
    r_initial = await get_exchange_data("initial")
    t_current = int(datetime.now().timestamp() / 300)
    p_total = await get_exchanged_pawcoin()
    v_total = await get_total_vimcoin()
    return r_initial * (1 + a * math.sin(t_current / b) + c * (p_total / v_total + d)) / 3


async def get_exchange_vimcoin(count: int) -> float:
    return round(count * await get_exchange_data(), 3)


@scheduler.scheduled_job("cron", minute="*", id="update_exchange")
async def _() -> None:
    origin_exchange = await calculate_exchange()
    exchange = round(origin_exchange, 3)
    async with aiofiles.open(path, "r+", encoding="utf-8") as f:
        data = json.loads(await f.read())
        data["exchange"] = exchange
        await f.seek(0)
        await f.write(json.dumps(data))
        await f.truncate()
    logger.info(f"PawCoin 汇率更新完成，最新汇率为 {exchange} ({origin_exchange})")


async def remove_pawcoin_form_bag(count: int, user_id: str) -> None:
    try:
        await remove_item_from_bag(user_id, get_location(), count or ALL)
    except ItemLockedError:
        await lang.finish("bag_error.locked", user_id)
    except ItemNotEnough as e:
        await lang.finish("bag_error.not_enough_item", user_id, e.have)


async def exchange(index: Match[int], count: int, user_id: str) -> None:
    if count < 0:
        await lang.finish("count.invalid_count", user_id)
    elif index.available and count >= 0:
        target_item = await get_target_item(index.result, count, user_id)
        count = count or target_item.stack.count
        target_item.stack.count -= count
    else:
        await remove_pawcoin_form_bag(count, user_id)
    await add_vimcoin(user_id, vimcoin_count := await get_exchange_vimcoin(count))
    await add_exchanged_count(user_id, count, vimcoin_count)
    await lang.finish("pcc.ok", count, vimcoin_count)
