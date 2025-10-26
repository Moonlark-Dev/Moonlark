import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional
from dotenv import find_dotenv, load_dotenv
import os
from fastapi.responses import PlainTextResponse
import httpx
import re
import traceback
import uvicorn
import datetime
from .config import Config
from nb_cli.cli.commands import run as nb_cli_run
from .database import get_mysql_dump, get_mysql_user, update_mysql_backup, init_db, send_db_update_to_master, parse_db_url, receive_db_chunk, get_received_chunks_status, complete_db_update
from .git_ops import commit_and_push_backup
from .moonlark import launch_moonlark
from .utils import test_connecting

from nb_cli.cli import run_sync
from nonebot.log import logger
from fastapi import FastAPI, File, HTTPException

class MoonlarkRecovery:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.app = FastAPI(lifespan=asynccontextmanager(self.lifespan))
        self.state: Literal["READY", "RUNNING", "STARTING", "WAITING_DISPATCH"] = "STARTING"
        self.nonebot_task = None
        self.waiting_for_dispatch = False  # 标记是否正在等待调度
        self.waiting_dispatch_deadline = 0  # 等待调度的截止时间
        self.app.get("/status")(self.get_status)
        self.app.get("/mysql/dump")(self.get_mysql_dump)
        self.app.get("/mysql/user")(self.get_mysql_user)
        self.app.post("/mysql/update")(self.update_mysql_backup)
        self.app.post("/mysql/update_chunk")(self.update_mysql_chunk)
        self.app.get("/mysql/chunk_status")(self.get_chunk_status)
        self.app.post("/mysql/update_complete")(self.complete_mysql_update)

    async def get_mysql_dump(self) -> PlainTextResponse:
        return await get_mysql_dump(self.config)

    async def get_mysql_user(self) -> dict[str, str,] | None:
        return await get_mysql_user(self.config)

    async def update_mysql_backup(self, dump: bytes = File()) -> dict:
        return await update_mysql_backup(self.config, dump.decode(), self.waiting_for_dispatch, self.waiting_dispatch_deadline)
    
    async def update_mysql_chunk(self, chunk_data: dict) -> dict:
        return await receive_db_chunk(self.config, chunk_data, self.waiting_for_dispatch, self.waiting_dispatch_deadline)
    
    async def get_chunk_status(self) -> dict:
        return await get_received_chunks_status()
    
    async def complete_mysql_update(self, total_chunks: int) -> dict:
        return await complete_db_update(self.config, total_chunks, self.waiting_for_dispatch, self.waiting_dispatch_deadline)
    


            

    def set_state(self, state: Literal["READY", "RUNNING", "STARTING", "WAITING_DISPATCH"]) -> None:
        self.state = state
        logger.info(f"State changed to {state}")



    async def wait_for_slave_updates(self) -> None:
        """等待从节点上传数据完成或超时"""
        self.waiting_for_dispatch = True
        start_time = asyncio.get_event_loop().time()
        initial_deadline = start_time + 20  # 初始20秒等待
        max_deadline = start_time + 5 * 60  # 最长5分钟
        
        logger.info("作为主节点，等待20秒以便其他节点上报数据库初始化数据")
        
        while asyncio.get_event_loop().time() < max_deadline:
            # 检查是否在初始20秒内
            current_time = asyncio.get_event_loop().time()
            if current_time < initial_deadline:
                # 在初始20秒内，直接等待剩余时间
                remaining_time = initial_deadline - current_time
                await asyncio.sleep(min(remaining_time, 1.0))  # 每秒检查一次
            else:
                # 超过初始20秒，检查是否有上传活动
                chunk_status = await get_received_chunks_status()
                received_chunks = chunk_status.get("received_chunks", [])
                total_chunks = chunk_status.get("total_chunks", 0)
                
                # 如果没有接收到任何块，或者已经接收完所有块，则退出等待
                if len(received_chunks) == 0 or len(received_chunks) >= total_chunks:
                    break
                
                # 如果还有块在传输中，继续等待
                logger.info(f"检测到从节点正在上传数据: {len(received_chunks)}/{total_chunks} 块已接收")
                await asyncio.sleep(1.0)  # 每秒检查一次
        
        self.waiting_for_dispatch = False
        logger.info("等待从节点上传数据完成或超时，准备启动服务")

    async def loop(self) -> None:
        if await self.is_master():
            self.set_state("WAITING_DISPATCH")
            await self.wait_for_slave_updates()
            self.set_state("READY")
        if not await self.is_master():
            try:
                await init_db(self.config)
                logger.info("数据库初始化成功")
            except Exception as e:
                logger.error(f"数据库初始化失败: {traceback.format_exc()}")
                # 初始化失败，等待重试
                await asyncio.sleep(10)
                return
        logger.info("Starting recovery server...")
        self.set_state("READY")
        while True:
            if self.state == "READY" and await self.is_master(): 
                await launch_moonlark(self.config, self.set_state)
            elif self.state == "RUNNING" and not await self.is_master():
                logger.info("作为从节点，等待主节点调度")
                if self.nonebot_task:
                    self.nonebot_task.cancel()
                
                # 执行git操作
                await commit_and_push_backup(self.config)
                await send_db_update_to_master(self.config, self.get_master)
                self.set_state("READY")
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

