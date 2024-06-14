from ..__main__ import quick_math, lang

@quick_math.assign("$main")
async def _() -> None:
    pass
