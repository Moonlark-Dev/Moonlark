import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional
from dotenv import find_dotenv, load_dotenv
import os
import os.path
import httpx
import os
import re
import subprocess
import traceback
import uvicorn
import datetime
from .config import Config
from nb_cli.cli.commands import run as nb_cli_run

from nb_cli.cli import run_sync
from nonebot.log import logger
from fastapi import FastAPI, HTTPException

async def test_connecting(url: str) -> bool:
    try:
        async with httpx.AsyncClient(base_url=url) as client:
            resp = await client.get("/status")
            return resp.status_code == 200
    except Exception:
        return False
        



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
    
    def parse_db_url(self, url: str) -> tuple[str, str, str, str, str]:
        """解析数据库连接URL，返回用户名、密码、主机、端口和数据库名
        
        Args:
            url: 数据库连接URL，格式为 mysql://username:password@host:port/database
            
        Returns:
            包含用户名、密码、主机、端口和数据库名的元组
            
        Raises:
            ValueError: 如果URL格式不正确
        """
        url_pattern = r"mysql\+aiomysql://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/([^/?]+)"
        match = re.match(url_pattern, url)
        
        if not match:
            raise ValueError(f"无法解析数据库连接字符串: {url}")
            
        username, password, host, port, database = match.groups()
        port = port or "3306"
        
        return username, password, host, port, database

    async def get_mysql_dump(self) -> str:
        if self.is_master():
            try:
                # 从 sqlalchemy_database_url 中解析数据库连接信息
                username, password, host, port, database = self.parse_db_url(self.config.sqlalchemy_database_url)
                
                # 执行 mysqldump 命令并获取输出
                # 使用环境变量传递密码，避免特殊字符问题
                import os
                os.environ["MYSQL_PWD"] = password
                command = [
                    "mysqldump",
                    f"-h{host}",
                    f"-P{port}",
                    f"-u{username}",
                    "--single-transaction",
                    "--routines",
                    "--triggers",
                    database
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    raise HTTPException(status_code=500, detail=f"数据库备份失败: {stderr.decode()}")
                
                # 返回SQL内容
                sql_content = stdout.decode('utf-8')
                
                # 同时保存到本地备份文件
                backup_path = os.path.join(self.config.recovery_local_backup_path, f"{database}_dump.sql")
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                with open(backup_path, "w", encoding='utf-8') as f:
                    f.write(sql_content)
                
                return sql_content
            except ValueError as e:
                raise HTTPException(status_code=500, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"执行备份时出错: {traceback.format_exc()}")
        else:
            raise HTTPException(status_code=403, detail="只有主节点可以执行数据库备份")

    async def get_mysql_user(self) -> Optional[dict[str, str]]:
        if self.is_master():
            return {
                "user": self.config.recovery_repl_user,
                "password": self.config.recovery_repl_password,
            }
        else:
            raise HTTPException(403)
            
    async def update_mysql_backup(self, dump: str) -> dict:
        """接收从其他节点发送的数据库备份并更新本地备份
        
        Args:
            dump: 从其他节点发送的数据库备份内容
            
        Returns:
            操作结果
        """
        # 检查是否在等待调度状态且在20秒的时间窗口内
        current_time = asyncio.get_event_loop().time()
        if not self.waiting_for_dispatch or current_time > self.waiting_dispatch_deadline:
            raise HTTPException(status_code=403, detail="不在等待调度状态或已超过时间窗口")
            
        if not await self.is_master():
            raise HTTPException(status_code=403, detail="只有主节点可以接收数据库更新")
            
        try:
            # 从 sqlalchemy_database_url 中解析数据库连接信息
            username, password, host, port, database = self.parse_db_url(self.config.sqlalchemy_database_url)
            
            # 保存备份到本地
            backup_path = os.path.join(self.config.recovery_local_backup_path, f"{database}_dump.sql")
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            with open(backup_path, "w", encoding='utf-8') as f:
                f.write(dump)
                
            logger.info(f"已接收并保存数据库更新: {backup_path}")
            
            return {"status": "success", "message": "数据库更新已成功保存"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"处理数据库更新时出错: {traceback.format_exc()}")

    def set_state(self, state: Literal["READY", "RUNNING", "STARTING", "WAITING_DISPATCH"]) -> None:
        self.state = state
        logger.info(f"State changed to {state}")

    async def launch_moonlark(self) -> None:
        self.set_state("RUNNING")
        logger.info("Launching MoonLark...")
        
        try:
            # 从 sqlalchemy_database_url 中解析数据库连接信息
            username, password, host, port, database = self.parse_db_url(self.config.sqlalchemy_database_url)
            
            # 检查是否需要停止数据库复制并设置为可读
            try:
                # 检查是否是从服务器（需要停止复制）
                is_slave = False
                # 使用环境变量传递密码，避免特殊字符问题
                os.environ["MYSQL_PWD"] = password
                check_slave_command = [
                    "mysql",
                    f"-h{host}",
                    f"-P{port}",
                    f"-u{username}",
                    "-e", "SHOW SLAVE STATUS\\G"
                ]

                process = await asyncio.create_subprocess_exec(
                    *check_slave_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                # 如果命令成功执行且输出不为空，说明存在从服务器配置
                if process.returncode == 0 and stdout.decode().strip():
                    is_slave = True
                    logger.info("检测到数据库配置为从服务器，将停止复制")

                # 只有在是从服务器时才执行停止复制命令
                if is_slave:
                    # 停止复制
                    # 环境变量已经在上面设置，这里直接使用
                    stop_replication_command = [
                        "mysql",
                        f"-h{host}",
                        f"-P{port}",
                        f"-u{username}",
                        "-e", "STOP SLAVE; RESET SLAVE ALL; SET GLOBAL read_only = OFF;"
                    ]
                
                    process = await asyncio.create_subprocess_exec(
                        *stop_replication_command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                
                    if process.returncode != 0:
                        logger.error(f"停止数据库复制失败: {stderr.decode()}")
                    else:
                        logger.info("成功停止数据库复制并设置为可写")
            except Exception as e:
                logger.error(f"停止数据库复制时出错: {traceback.format_exc()}")
            
            # 在本地备份文件夹运行 git pull
            try:
                original_cwd = os.getcwd()  # 保存当前工作目录
                os.chdir(self.config.recovery_local_backup_path)
                process = await asyncio.create_subprocess_exec(
                    "git", "pull",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"Git pull 失败: {stderr.decode()}")
                else:
                    logger.info("成功从远程仓库拉取最新备份")
            except Exception as e:
                logger.error(f"执行 git pull 时出错: {traceback.format_exc()}")
            finally:
                # 确保恢复原来的工作目录
                try:
                    os.chdir(original_cwd)
                except:
                    pass
                
        except ValueError as e:
            logger.error(f"解析数据库连接信息失败: {traceback.format_exc()}")
        
        logger.info("向 Nonebot2 发出启动指令 ...")
        self.nonebot_task = asyncio.create_task(run_sync(nb_cli_run)())

    async def init_db(self) -> None:
        self.set_state("STARTING")
        
        # 获取上游服务器列表
        upstream_servers = await self.get_upstream_servers()
        if not upstream_servers:
            raise Exception("没有可用的上游服务器")
            
        master_server = upstream_servers[0]
        logger.info(f"使用上游服务器: {master_server}")
        
        # 从 sqlalchemy_database_url 中解析本地数据库连接信息
        try:
            local_username, local_password, local_host, local_port, local_database = self.parse_db_url(self.config.sqlalchemy_database_url)
        except ValueError as e:
            raise Exception(f"解析数据库连接信息失败: {traceback.format_exc()}")
        
        try:
            # 从上游获取最新的数据库备份
            backup_url = f"{master_server}/mysql/dump"
            async with httpx.AsyncClient() as client:
                response = await client.get(backup_url)
                if response.status_code != 200:
                    raise Exception(f"从上游获取数据库备份失败: {response.status_code}")
                    
                # 保存备份文件
                backup_path = Path("backup.sql")
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                with open(backup_path, "wb") as f:
                    f.write(response.content)
                    
                logger.info(f"已从上游获取数据库备份: {backup_path}")
                
            # 从上游获取复制用户信息
            user_url = f"{master_server}/mysql/user"
            async with httpx.AsyncClient() as client:
                response = await client.get(user_url)
                if response.status_code != 200:
                    raise Exception(f"从上游获取复制用户信息失败: {response.status_code}")
                    
                user_info = response.json()
                repl_user = user_info.get("user")
                repl_password = user_info.get("password")
                
                if not repl_user or not repl_password:
                    raise Exception("上游返回的复制用户信息不完整")
                    
                logger.info(f"已获取复制用户信息: {repl_user}")
                
            # 恢复数据库
            # 使用环境变量传递密码，避免特殊字符问题
            os.environ["MYSQL_PWD"] = local_password
            restore_command = [
                "mysql",
                f"-h{local_host}",
                f"-P{local_port}",
                f"-u{local_username}",
                local_database
            ]
            
            with open(backup_path, "r") as f:
                process = await asyncio.create_subprocess_exec(
                    *restore_command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate(input=f"source {backup_path.as_posix()}".encode())
                
            if process.returncode != 0:
                raise Exception(f"数据库恢复失败: {stderr.decode()}")
                
            logger.info("成功恢复数据库")
            
            # 配置复制
            # 获取主服务器信息
            master_url = f"{master_server}/status"
            async with httpx.AsyncClient() as client:
                response = await client.get(master_url)
                if response.status_code != 200:
                    raise Exception(f"获取主服务器状态失败: {response.status_code}")
                    
                master_status = response.json()
                if not master_status.get("master"):
                    raise Exception(f"上游服务器 {master_server} 不是主服务器")
            
            # 从主服务器URL中解析连接信息
            master_match = re.match(r"https?://([^:/]+)(?::(\d+))?", master_server)
            if not master_match:
                raise Exception(f"无法解析主服务器URL: {master_server}")
                
            master_host, master_port = master_match.groups()
            master_port = master_port or "3306"
            
            # 配置并启动复制
            # 使用环境变量传递密码，避免特殊字符问题
            os.environ["MYSQL_PWD"] = local_password
            configure_replication_command = [
                "mysql",
                f"-h{local_host}",
                f"-P{local_port}",
                f"-u{local_username}",
                "-e", f"CHANGE MASTER TO MASTER_HOST='{master_host}', MASTER_PORT={master_port}, MASTER_USER='{repl_user}', MASTER_PASSWORD='{repl_password}', MASTER_AUTO_POSITION=1; START SLAVE; SET GLOBAL read_only = ON;"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *configure_replication_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"配置复制失败: {stderr.decode()}")
                
            logger.info("成功配置并启动数据库复制")
            
        except Exception as e:
            raise Exception(f"初始化数据库时出错: {traceback.format_exc()}")

    async def loop(self) -> None:
        if await self.is_master():
            self.waiting_for_dispatch = True
            self.waiting_dispatch_deadline = asyncio.get_event_loop().time() + 20
            self.set_state("WAITING_DISPATCH")
            logger.info("作为主节点，等待20秒以便其他节点上报数据库初始化数据")
            
            # 等待20秒
            await asyncio.sleep(20)
            self.waiting_for_dispatch = False
            logger.info("等待调度时间结束，准备启动服务")
        if not await self.is_master():
            try:
                await self.init_db()
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
                await self.launch_moonlark()
            elif self.state == "RUNNING" and not await self.is_master():
                logger.info("作为从节点，等待主节点调度")
                if self.nonebot_task:
                    self.nonebot_task.cancel()
                
                # 执行git操作
                await self.commit_and_push_backup()
                await self.send_db_update_to_master()
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
        
    async def send_db_update_to_master(self) -> None:
        """发送数据库更新到主节点"""
        master = await self.get_master()
        if master:
            try:
                # 从 sqlalchemy_database_url 中解析数据库连接信息
                username, password, host, port, database = self.parse_db_url(self.config.sqlalchemy_database_url)
                
                # 执行 mysqldump 命令获取数据库备份
                # 使用环境变量传递密码，避免特殊字符问题
                import os
                os.environ["MYSQL_PWD"] = password
                command = [
                    "mysqldump",
                    f"-h{host}",
                    f"-P{port}",
                    f"-u{username}",
                    "--single-transaction",
                    "--routines",
                    "--triggers",
                    database
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"生成数据库备份失败: {stderr.decode()}")
                else:
                    # 发送备份到主节点
                    update_url = f"{master}/mysql/update"
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            update_url,
                            files={"dump": ("dump.sql", stdout.decode('utf-8'), "text/sql")}
                        )
                        
                        if response.status_code == 200:
                            logger.info("成功向主节点发送数据库更新")
                        else:
                            logger.error(f"向主节点发送数据库更新失败: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"向主节点发送数据库更新时出错: {traceback.format_exc()}")

    async def commit_and_push_backup(self):
        """在本地备份文件夹执行 git commit 和 git push"""
        try:
            os.chdir(self.config.recovery_local_backup_path)
            # 添加所有更改
            process = await asyncio.create_subprocess_exec(
                "git", "add", ".",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Git add 失败: {stderr.decode()}")
                return
                
            # 提交更改
            commit_message = f"自动提交: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            process = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", commit_message,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Git commit 失败: {stderr.decode()}")
                return
                
            # 推送更改
            process = await asyncio.create_subprocess_exec(
                "git", "push",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Git push 失败: {stderr.decode()}")
            else:
                logger.info("成功提交并推送本地备份到远程仓库")
        except Exception as e:
            logger.error(f"执行 git 操作时出错: {traceback.format_exc()}")
    
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

