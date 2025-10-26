import asyncio
from fastapi.responses import PlainTextResponse
import httpx
import os
import re
import traceback
import base64
import hashlib
from pathlib import Path
from typing import Optional, Tuple, List, Dict
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


# 存储接收到的块数据的全局变量（在实际应用中可能需要持久化存储）
_received_chunks: Dict[int, str] = {}
_total_chunks: int = 0

async def update_mysql_backup(config: Config, dump: str, waiting_for_dispatch: bool, waiting_dispatch_deadline: float) -> dict:
    """接收从其他节点发送的数据库备份并更新本地备份（兼容旧版本）
    
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
        # 保存备份到本地
        backup_path = Path("dump.sql")
        with open(backup_path, "w", encoding='utf-8') as f:
            f.write(dump)
             
        logger.info(f"已接收并保存数据库更新: {backup_path}")

        return {"status": "success", "message": "数据库更新已成功保存"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理数据库更新时出错: {traceback.format_exc()}")

async def receive_db_chunk(config: Config, chunk_data: dict, waiting_for_dispatch: bool, waiting_dispatch_deadline: float) -> dict:
    """接收从其他节点发送的数据库备份块
    
    Args:
        config: 配置对象
        chunk_data: 块数据
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
        global _received_chunks, _total_chunks
        
        chunk_index = chunk_data["chunk_index"]
        total_chunks = chunk_data["total_chunks"]
        data = chunk_data["data"]
        checksum = chunk_data["checksum"]
        
        # 更新总块数
        _total_chunks = total_chunks
        
        # 解码数据
        chunk_bytes = base64.b64decode(data.encode('utf-8'))
        
        # 验证校验和
        calculated_checksum = hashlib.md5(chunk_bytes).hexdigest()
        if calculated_checksum != checksum:
            raise HTTPException(status_code=400, detail=f"块 {chunk_index} 校验和不匹配")
        
        # 存储块数据
        _received_chunks[chunk_index] = chunk_bytes.decode('utf-8')
        
        # 计算接收进度
        received_count = len(_received_chunks)
        progress = received_count / total_chunks * 100
        logger.info(f"接收进度: {progress:.1f}% ({received_count}/{total_chunks})")
        logger.debug(f"已接收块 {chunk_index+1}/{total_chunks} ({len(chunk_bytes)} bytes)")
        
        return {"status": "success", "message": f"块 {chunk_index} 接收成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理数据库块时出错: {traceback.format_exc()}")

async def get_received_chunks_status() -> dict:
    """获取已接收的块状态
    
    Returns:
        包含已接收块信息的字典
    """
    global _received_chunks, _total_chunks
    return {
        "received_chunks": list(_received_chunks.keys()),
        "total_chunks": _total_chunks
    }

async def complete_db_update(config: Config, total_chunks: int, waiting_for_dispatch: bool, waiting_dispatch_deadline: float) -> dict:
    """完成数据库更新，将所有接收到的块合并成完整的备份文件
    
    Args:
        config: 配置对象
        total_chunks: 总块数
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
        global _received_chunks, _total_chunks
        
        # 检查是否所有块都已接收
        if len(_received_chunks) != total_chunks:
            missing_chunks = set(range(total_chunks)) - set(_received_chunks.keys())
            raise HTTPException(status_code=400, detail=f"缺少块: {missing_chunks}")
        
        # 按顺序合并所有块
        merged_data = ""
        for i in range(total_chunks):
            if i in _received_chunks:
                merged_data += _received_chunks[i]
            else:
                raise HTTPException(status_code=500, detail=f"缺少块 {i}")
        
        # 保存合并后的备份到本地
        backup_path = Path("dump.sql")
        with open(backup_path, "w", encoding='utf-8') as f:
            f.write(merged_data)
             
        logger.info(f"已接收并合并数据库更新: {backup_path} ({len(merged_data)} bytes)")
        
        # 清空临时存储
        _received_chunks.clear()
        _total_chunks = 0
        
        return {"status": "success", "message": "数据库更新已成功保存"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"完成数据库更新时出错: {traceback.format_exc()}")


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
    
    os.environ["MYSQL_PWD"] = local_password
    try:
        # 从上游获取最新的数据库备份
        backup_url = f"{master_server}/mysql/dump"
        # 增加超时设置以适应低带宽环境
        timeout = httpx.Timeout(120.0, connect=30.0, read=60.0, write=60.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(backup_url)
            if response.status_code != 200:
                raise Exception(f"从上游获取数据库备份失败: {response.status_code}")
            buf = response.content
            logger.info(f"已从上游获取数据库备份 ({len(buf)} bytes)")
        

        restore_command = [
            "mysql",
            f"-h{local_host}",
            f"-P{local_port}",
            f"-u{local_username}",
            local_database
        ]
        
        process = await asyncio.create_subprocess_exec(
            *restore_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate(input=buf)

        # 从上游获取复制用户信息
        user_url = f"{master_server}/mysql/user"
        # 增加超时设置以适应低带宽环境
        timeout = httpx.Timeout(120.0, connect=30.0, read=60.0, write=60.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(user_url)
            if response.status_code != 200:
                raise Exception(f"从上游获取复制用户信息失败: {response.status_code}")
                
            user_info = response.json()
            repl_user = user_info.get("user")
            repl_password = user_info.get("password")
            
            if not repl_user or not repl_password:
                raise Exception("上游返回的复制用户信息不完整")
                
            logger.info(f"已获取复制用户信息: {repl_user}")
        
            
        if process.returncode != 0:
            raise Exception(f"数据库恢复失败: {stderr.decode()}")
            
        logger.info("成功恢复数据库")
        
        # 配置复制
        # 获取主服务器信息
        master_url = f"{master_server}/status"
        # 增加超时设置以适应低带宽环境
        timeout = httpx.Timeout(120.0, connect=30.0, read=60.0, write=60.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
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
        
        configure_replication_command = [
            "mysql",
            f"-h{local_host}",
            f"-P{local_port}",
            f"-u{local_username}",
            "--skip-ssl",
            local_database,
            "-e", f"STOP SLAVE; RESET SLAVE ALL; CHANGE MASTER TO MASTER_HOST='{master_host}', MASTER_PORT={master_port}, MASTER_USER='{repl_user}', MASTER_PASSWORD='{repl_password}', MASTER_SSL=0; START SLAVE;"
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


CHUNK_SIZE = 64 * 1024  # 64KB chunks

async def send_db_update_to_master(config: Config, get_master_func) -> None:
    """发送数据库更新到主节点（使用分块传输）
    
    Args:
        config: 配置对象
        get_master_func: 获取主节点地址的函数
    """
    master = await get_master_func()
    logger.info("开始发送数据库更新到主节点 ...")
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
                # 分块发送备份到主节点
                dump_data = stdout.decode('utf-8')
                await _send_db_dump_in_chunks(master, dump_data)
        except Exception as e:
            logger.error(f"向主节点发送数据库更新时出错: {traceback.format_exc()}")

async def _send_db_dump_in_chunks(master: str, dump_data: str) -> None:
    """分块发送数据库备份数据
    
    Args:
        master: 主节点地址
        dump_data: 数据库备份数据
    """
    # 将数据分割成块
    dump_bytes = dump_data.encode('utf-8')
    total_chunks = (len(dump_bytes) + CHUNK_SIZE - 1) // CHUNK_SIZE
    logger.info(f"开始分块传输数据库备份，总大小: {len(dump_bytes)} bytes, 总块数: {total_chunks}")
    
    # 获取主节点已接收的块状态
    received_chunks = await _get_received_chunks_status(master, total_chunks)
    if received_chunks is None:
        logger.error("无法获取主节点已接收块状态，使用全量传输")
        received_chunks = set()
    
    # 创建具有适当超时设置的HTTP客户端
    # 增加超时时间以适应低带宽环境
    timeout = httpx.Timeout(120.0, connect=30.0, read=60.0, write=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # 逐个发送未接收的块
        sent_chunks = len(received_chunks)  # 已发送的块数
        for i in range(total_chunks):
            # 如果块已被接收，跳过
            if i in received_chunks:
                logger.debug(f"块 {i} 已被接收，跳过传输")
                sent_chunks += 1
                continue
                
            # 获取当前块数据
            start = i * CHUNK_SIZE
            end = min((i + 1) * CHUNK_SIZE, len(dump_bytes))
            chunk_data = dump_bytes[start:end]
            
            # 计算校验和
            checksum = hashlib.md5(chunk_data).hexdigest()
            
            # 编码块数据
            encoded_data = base64.b64encode(chunk_data).decode('utf-8')
            
            # 准备块数据
            chunk_payload = {
                "chunk_index": i,
                "total_chunks": total_chunks,
                "data": encoded_data,
                "checksum": checksum
            }
            
            # 发送块数据
            update_url = f"{master}/mysql/update_chunk"
            max_retries = 5  # 增加重试次数
            
            # 计算传输进度
            progress = (sent_chunks + 1) / total_chunks * 100
            logger.info(f"传输进度: {progress:.1f}% ({sent_chunks + 1}/{total_chunks})")
            
            for attempt in range(max_retries):
                try:
                    response = await client.post(update_url, json=chunk_payload)
                    
                    if response.status_code == 200:
                        logger.info(f"成功发送块 {i+1}/{total_chunks} ({len(chunk_data)} bytes)")
                        sent_chunks += 1
                        break  # 成功则退出重试循环
                    else:
                        logger.error(f"发送块 {i} 失败: {response.status_code} - {response.text}")
                        if attempt < max_retries - 1:
                            wait_time = 2 ** attempt  # 指数退避
                            logger.info(f"将在{wait_time}秒后进行第{attempt + 2}次重试...")
                            await asyncio.sleep(wait_time)
                except httpx.ReadError as e:
                    logger.error(f"网络读取错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # 指数退避
                        logger.info(f"将在{wait_time}秒后进行第{attempt + 2}次重试...")
                        await asyncio.sleep(wait_time)
                except httpx.ConnectError as e:
                    logger.error(f"连接错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # 指数退避
                        logger.info(f"将在{wait_time}秒后进行第{attempt + 2}次重试...")
                        await asyncio.sleep(wait_time)
                except Exception as e:
                    logger.error(f"发送块 {i} 时发生未预期的错误: {traceback.format_exc()}")
                    break  # 对于未知错误，不进行重试
            
            else:
                logger.error(f"经过{max_retries}次尝试后仍无法发送块 {i}")
                raise Exception(f"无法发送数据块 {i}")
        
        # 通知主节点所有块已发送完成
        try:
            finish_url = f"{master}/mysql/update_complete"
            response = await client.post(finish_url, json={"total_chunks": total_chunks})
            if response.status_code == 200:
                logger.info("成功通知主节点数据库更新传输完成")
            else:
                logger.error(f"通知主节点传输完成失败: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"通知主节点传输完成时出错: {traceback.format_exc()}")

async def _get_received_chunks_status(master: str, total_chunks: int) -> Optional[set]:
    """获取主节点已接收的块状态
    
    Args:
        master: 主节点地址
        total_chunks: 总块数
        
    Returns:
        已接收的块序号集合，如果获取失败则返回None
    """
    try:
        status_url = f"{master}/mysql/chunk_status"
        timeout = httpx.Timeout(30.0, connect=10.0, read=15.0, write=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(status_url)
            if response.status_code == 200:
                status_data = response.json()
                received_chunks = set(status_data.get("received_chunks", []))
                logger.info(f"主节点已接收 {len(received_chunks)}/{total_chunks} 个块")
                return received_chunks
            else:
                logger.warning(f"获取主节点块状态失败: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        logger.warning(f"获取主节点块状态时出错: {traceback.format_exc()}")
        return None


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
        # 增加超时设置以适应低带宽环境
        timeout = httpx.Timeout(30.0, connect=10.0, read=15.0, write=15.0)
        async with httpx.AsyncClient(base_url=url, timeout=timeout) as client:
            resp = await client.get("/status")
            return resp.status_code == 200
    except Exception:
        return False