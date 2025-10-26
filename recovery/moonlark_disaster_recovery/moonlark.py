import asyncio
import os
import traceback
from pathlib import Path
from typing import Literal
from nonebot.log import logger
from nb_cli.cli import run_sync
from nb_cli.cli.commands import run as nb_cli_run


async def launch_moonlark(config, set_state_func):
    """启动MoonLark服务
    
    Args:
        config: 配置对象
        set_state_func: 设置状态的函数
    """
    set_state_func("RUNNING")
    logger.info("Launching MoonLark...")
    
    try:
        # 从 sqlalchemy_database_url 中解析数据库连接信息
        from .database import parse_db_url
        username, password, host, port, database = parse_db_url(config.sqlalchemy_database_url)
        
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
                    "-e", "STOP SLAVE; RESET SLAVE ALL;"
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
            original_cwd = Path.cwd()  # 保存当前工作目录
            os.chdir(Path(config.recovery_local_backup_path))
            process = await asyncio.create_subprocess_exec(
                "git", "reset", "--hard", "HEAD" 
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
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
                os.chdir(Path(original_cwd))
            except:
                pass
                
    except ValueError as e:
        logger.error(f"解析数据库连接信息失败: {traceback.format_exc()}")
    
    logger.info("向 Nonebot2 发出启动指令 ...")
    nonebot_task = asyncio.create_task(run_sync(nb_cli_run)())
    return nonebot_task