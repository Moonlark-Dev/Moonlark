import asyncio
import os
import traceback
from pathlib import Path
import datetime
from nonebot.log import logger


async def commit_and_push_backup(config) -> None:
    """在本地备份文件夹执行 git commit 和 git push
    
    Args:
        config: 配置对象
    """
    try:
        original_cwd = Path.cwd()  # 保存当前工作目录
        os.chdir(Path(config.recovery_local_backup_path))
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
    finally:
        # 确保恢复原来的工作目录
        try:
            os.chdir(Path(original_cwd))
        except:
            pass