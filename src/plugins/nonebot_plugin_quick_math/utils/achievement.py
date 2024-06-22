from ...nonebot_plugin_item.registry.registry import ResourceLocation
from ...nonebot_plugin_achievement import unlock_achievement


def get_achievement_location(path: str) -> ResourceLocation:
    return ResourceLocation("quick_math", path)


async def update_achievements_status(
    user_id: str, answered: int, point: int, correct_rate: float, skipped: int
) -> None:
    await unlock_achievement(get_achievement_location("getting_started"), user_id, answered)
    await unlock_achievement(get_achievement_location("100_questions_master"), user_id, answered)
    await unlock_achievement(get_achievement_location("escape_artist"), user_id, skipped)
    await unlock_achievement(get_achievement_location("a_little_bit_adds_up"), user_id, point)
    if point >= 200:
        await unlock_achievement(get_achievement_location("showing_off"), user_id)
    if point >= 1000:
        await unlock_achievement(get_achievement_location("math_master"), user_id)
    if point >= 2000 and correct_rate >= 0.95:
        await unlock_achievement(get_achievement_location("computing_genius"), user_id)
    if answered >= 200 and correct_rate >= 1:
        await unlock_achievement(get_achievement_location("master"), user_id)
