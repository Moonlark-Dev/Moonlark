import asyncio
from contextlib import asynccontextmanager
from typing import Literal, Optional
from dotenv import find_dotenv, load_dotenv
import httpx
import uvicorn
from .config import Config
from nb_cli.cli.commands import run as nb_cli_run

from nb_cli.cli import run_sync
from nonebot.log import logger
from fastapi import FastAPI, HTTPException

async def test_connecting(url: str) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False
        



class MoonlarkRecovery:

    def __init__(self, config: Config) -> None:
        self.config = config
        self.app = FastAPI(lifespan=asynccontextmanager(self.lifespan))
        self.state: Literal["READY", "RUNNING", "STARTING"] = "STARTING"
        self.nonebot_task = None
        self.app.get("/status")(self.get_status)
        self.app.get("/mysql/dump")(self.get_mysql_dump)
        self.app.get("/mysql/user")(self.get_mysql_user)

    async def get_mysql_dump(self) -> str:
        if self.is_master():
            # TODO 调用 mysqldump 命令进行备份，使用来自 sqlalchemy_database_url 的用户名和密码
            pass
        else:
            raise HTTPException(403)

    async def get_mysql_user(self) -> Optional[dict[str, str]]:
        if self.is_master():
            return {
                "user": self.config.recovery_repl_user,
                "password": self.config.recovery_repl_password,
            }
        else:
            raise HTTPException(403)

    def set_state(self, state: Literal["READY", "RUNNING", "STARTING"]) -> None:
        self.state = state
        logger.info(f"State changed to {state}")

    async def launch_moonlark(self) -> None:
        self.set_state("RUNNING")
        logger.info("Launching MoonLark...")
        # TODO 停止数据库复制并设置为可读，在本地备份文件夹运行 git pull
        self.nonebot_task = asyncio.create_task(run_sync(nb_cli_run)())

    async def init_db(self) -> None:
        self.set_state("STARTING")
        # TODO 与上游比对数据库，如果不匹配则重新从上游拉取最新的数据库 dump，将其覆盖到并配置 GTID

    async def loop(self) -> None:
        if not await self.is_master():
            await self.init_db()
        logger.info("Starting recovery server...")
        self.set_state("READY")
        while True:
            if self.state == "READY" and await self.is_master(): 
                await self.launch_moonlark()
            elif self.state == "RUNNING" and not self.is_master():
                pass        # 暂时不用处理
            await asyncio.sleep(10)
    
    async def lifespan(self, _: FastAPI):
        asyncio.create_task(self.loop())
        yield

    async def get_status(self):
        return {
            "state": self.state,
            "master": await self.is_master()
        }

    async def get_master(self) -> Optional[str]:
        return (await self.get_upstream_servers())[0] if not await self.is_master() else None

    async def get_upstream_servers(self) -> list[str]:
        return [u for u in self.config.recovery_upstream_servers if await test_connecting(u)]

    async def is_master(self) -> bool:
        return len(await self.get_upstream_servers()) == 0


if __name__ == "__main__":
    if (not load_dotenv()) and not load_dotenv(find_dotenv(".env.prod")):
        raise Exception("No .env file found")
    config = Config(**{key.lower(): value for key, value in os.environ.items()})       # type: ignore
    recovery = MoonlarkRecovery(config)
    uvicorn.run(recovery.app, host="0.0.0.0", port=recovery.config.recovery_port)

