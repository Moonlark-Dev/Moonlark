import asyncio
from fastapi.responses import PlainTextResponse
import httpx
import os
import re
import traceback
from pathlib import Path
from typing import Optional, Tuple
from fastapi import HTTPException
from nonebot.log import logger
from .config import Config


def parse_db_url(url: str) -> Tuple[str, str, str, str, str]:
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


async def get_mysql_dump(config: Config) -> PlainTextResponse:
    """获取MySQL数据库的备份
    
    Args:
        config: 配置对象
        
    Returns:
        数据库备份的SQL内容
        
    Raises:
        HTTPException: 如果备份失败或不是主节点
    """
    # 检查是否是主节点
    if not await _is_master(config):
        raise HTTPException(status_code=403, detail="只有主节点可以执行数据库备份")
        
    try:
        # 从 sqlalchemy_database_url 中解析数据库连接信息
        username, password, host, port, database = parse_db_url(config.sqlalchemy_database_url)
        
        # 执行 mysqldump 命令并获取输出
        # 使用环境变量传递密码，避免特殊字符问题
        os.environ["MYSQL_PWD"] = password
        command = [
            "mysqldump",
            f"-h{host}",
            f"-P{port}",
            f"-u{username}",
            "--single-transaction",
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
        # backup_path = Path(config.recovery_local_backup_path) / f"{database}_dump.sql"
        # os.makedirs(Path(backup_path).parent, exist_ok=True)
        # with open(backup_path, "w", encoding='utf-8') as f:
        #     f.write(sql_content)
        
        return PlainTextResponse(sql_content)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行备份时出错: {traceback.format_exc()}")


async def get_mysql_user(config: Config) -> Optional[dict[str, str]]:
    """获取MySQL复制用户信息
    
    Args:
        config: 配置对象
        
    Returns:
        包含用户名和密码的字典
        
    Raises:
        HTTPException: 如果不是主节点
    """
    if not await _is_master(config):
        raise HTTPException(403)
        
    return {
        "user": config.recovery_repl_user,
        "password": config.recovery_repl_password,
    }


async def update_mysql_backup(config: Config, dump: str, waiting_for_dispatch: bool, waiting_dispatch_deadline: float) -> dict:
    """接收从其他节点发送的数据库备份并更新本地备份
    
    Args:
        config: 配置对象
        dump: 从其他节点发送的数据库备份内容
        waiting_for_dispatch: 是否在等待调度状态
        waiting_dispatch_deadline: 等待调度的截止时间
        
    Returns:
        操作结果
        
    Raises:
        HTTPException: 如果不在等待调度状态或已超过时间窗口，或不是主节点
    """
    # 检查是否在等待调度状态且在20秒的时间窗口内
    current_time = asyncio.get_event_loop().time()
    if not waiting_for_dispatch or current_time > waiting_dispatch_deadline:
        raise HTTPException(status_code=403, detail="不在等待调度状态或已超过时间窗口")
        
    if not await _is_master(config):
        raise HTTPException(status_code=403, detail="只有主节点可以接收数据库更新")
        
    try:
        # 从 sqlalchemy_database_url 中解析数据库连接信息
        username, password, host, port, database = parse_db_url(config.sqlalchemy_database_url)
        
        # 保存备份到本地
        backup_path = Path(config.recovery_local_backup_path) / f"{database}_dump.sql"
        os.makedirs(Path(backup_path).parent, exist_ok=True)
        with open(backup_path, "w", encoding='utf-8') as f:
            f.write(dump)
            
        logger.info(f"已接收并保存数据库更新: {backup_path}")
        
        return {"status": "success", "message": "数据库更新已成功保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理数据库更新时出错: {traceback.format_exc()}")


async def init_db(config: Config) -> None:
    """初始化数据库，从上游服务器获取备份并配置复制
    
    Args:
        config: 配置对象
        
    Raises:
        Exception: 如果初始化失败
    """
    # 获取上游服务器列表
    upstream_servers = await _get_upstream_servers(config)
    if not upstream_servers:
        raise Exception("没有可用的上游服务器")
        
    master_server = upstream_servers[0]
    logger.info(f"使用上游服务器: {master_server}")
    
    # 从 sqlalchemy_database_url 中解析本地数据库连接信息
    try:
        local_username, local_password, local_host, local_port, local_database = parse_db_url(config.sqlalchemy_database_url)
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
                stdin=f,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
        backup_path.unlink()
            
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
        master_port =  "3306"
        
        # 配置并启动复制
        # 使用环境变量传递密码，避免特殊字符问题
        os.environ["MYSQL_PWD"] = local_password
        configure_replication_command = [
            "mysql",
            f"-h{local_host}",
            f"-P{local_port}",
            f"-u{local_username}",
            "-e", f"CHANGE MASTER TO MASTER_HOST='{master_host}', MASTER_PORT={master_port}, MASTER_USER='{repl_user}', MASTER_PASSWORD='{repl_password}', MASTER_SSL=0, MASTER_SSL_VERIFY_SERVER_CERT=0; START SLAVE; SET GLOBAL read_only = ON;"
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


async def send_db_update_to_master(config: Config, get_master_func) -> None:
    """发送数据库更新到主节点
    
    Args:
        config: 配置对象
        get_master_func: 获取主节点地址的函数
    """
    master = await get_master_func()
    if master:
        try:
            # 从 sqlalchemy_database_url 中解析数据库连接信息
            username, password, host, port, database = parse_db_url(config.sqlalchemy_database_url)
            # 执行 mysqldump 命令获取数据库备份
            # 使用环境变量传递密码，避免特殊字符问题
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


async def _is_master(config: Config) -> bool:
    """检查是否为主节点
    
    Args:
        config: 配置对象
        
    Returns:
        是否为主节点
    """
    return len(await _get_upstream_servers(config)) == 0


async def _get_upstream_servers(config: Config) -> list[str]:
    """获取可用的上游服务器列表
    
    Args:
        config: 配置对象
        
    Returns:
        可用的上游服务器列表
    """
    return [u for u in config.recovery_upstream_servers if await _test_connecting(u)]


async def _test_connecting(url: str) -> bool:
    """测试连接到指定URL
    
    Args:
        url: 要测试的URL
        
    Returns:
        连接是否成功
    """
    try:
        async with httpx.AsyncClient(base_url=url) as client:
            resp = await client.get("/status")
            return resp.status_code == 200
    except Exception:
        return False