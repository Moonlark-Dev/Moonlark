from httpx import AsyncClient


async def get_game_version() -> float:
    async with AsyncClient() as client:
        resp = await client.get("https://hyp-api.mihoyo.com/hyp/hyp-connect/api/getGameBranches?launcher_id=jGHBHlcOq1&language=zh-cn&game_ids[]=64kMb5iAWu")
        return float(resp.json()["data"]["game_branches"][0]["main"]["tag"][:-2])