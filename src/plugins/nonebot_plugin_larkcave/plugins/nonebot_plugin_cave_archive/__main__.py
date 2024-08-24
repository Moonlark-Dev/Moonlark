import json
from datetime import datetime
import traceback
from ..nonebot_plugin_cave_remove.models import RemovedCave
from nonebot_plugin_apscheduler import scheduler
from sqlalchemy import select
from nonebot.log import logger
from nonebot_plugin_orm import AsyncSession, get_session
from nonebot_plugin_localstore import get_data_dir
from ...models import CaveData, ImageData
from ..nonebot_plugin_cave_comment.get import get_comment_list
import aiofiles
import time

data_dir = get_data_dir("nonebot_plugin_cave_archive")


async def get_comments(cave_id: int, session: AsyncSession) -> list[dict[str, str]]:
    comment_list = await get_comment_list(cave_id, session)
    comments = []
    for comment in comment_list:
        comments.append(
            {"id": comment.id, "content": comment.content, "author": comment.author, "time": comment.time.timestamp()}
        )
        await session.delete(comment)
    await session.commit()
    return comments


async def archive_cave(cave_id: int, session: AsyncSession) -> None:
    path = data_dir.joinpath(f"{cave_id}_{str(time.time()).replace('.', '_')}")
    path.mkdir(exist_ok=True)
    cave_data = await session.get_one(CaveData, {"id": cave_id})
    async with aiofiles.open(path.joinpath("cave.json"), "w", encoding="utf-8") as f:
        await f.write(
            json.dumps(
                {
                    "id": cave_id,
                    "author": cave_data.author,
                    "content": cave_data.content,
                    "time": cave_data.time.timestamp(),
                    "comments": await get_comments(cave_id, session),
                }
            )
        )
    await session.delete(cave_data)
    await session.commit()
    images = (await session.scalars(select(ImageData).where(ImageData.belong == cave_id))).all()
    for image in images:
        async with aiofiles.open(path.joinpath(f"{image.id}_{image.name}"), "wb") as f:
            await f.write(image.data)
        await session.delete(image)
        await session.commit()
    logger.success(f"已归档回声洞 {cave_id} 于 {path.as_posix()}")
    await session.close()


@scheduler.scheduled_job("cron", day="*", id="archive_removed_cave")
async def _() -> None:
    session = get_session()
    removed_cave_list = (await session.scalars(select(RemovedCave))).all()
    now = datetime.now()
    for data in removed_cave_list:
        if now <= data.expiration_time:
            continue
        logger.info(f"正在归档回声洞 {data.id} ...")
        try:
            await archive_cave(data.id, session)
        except Exception:
            logger.warning(f"归档回声洞 {data.id} 时出现错误: {traceback.format_exc()}")
    logger.info("回声洞归档检查完成！")
    await session.close()
