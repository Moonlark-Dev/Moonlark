import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from nonebot import get_driver, logger
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Alconna, Subcommand, on_alconna
from nonebot_plugin_larklang.__main__ import LangHelper
from nonebot_plugin_larkutils import get_user_id

from .config import config

lang = LangHelper()

# 创建命令处理器
version_alc = Alconna(
    "version",
    Subcommand("show", help_text="显示当前版本信息"),
    Subcommand("upgrade", help_text="拉取最新代码并更新（SUPERUSER）"),
)
version_cmd = on_alconna(version_alc, permission=SUPERUSER)


def run_command(cmd: list[str], cwd: Optional[Path] = None) -> tuple[int, str, str]:
    """运行任意命令并返回结果"""
    project_root = cwd or config.version_manager_project_root.resolve()

    try:
        result = subprocess.run(
            cmd, cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="ignore"
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def run_git_command(args: list[str], cwd: Optional[Path] = None) -> tuple[int, str, str]:
    """运行 git 命令并返回结果"""
    git_path = config.version_manager_git_path
    return run_command([git_path] + args, cwd)


def run_nb_command(args: list[str], cwd: Optional[Path] = None) -> tuple[int, str, str]:
    """运行 nb_cli 命令并返回结果"""
    nb_path = config.version_manager_nb_path
    return run_command([nb_path] + args, cwd)


def run_poetry_command(args: list[str], cwd: Optional[Path] = None) -> tuple[int, str, str]:
    """运行 poetry 命令并返回结果"""
    return run_command(["poetry"] + args, cwd)


async def get_version_info() -> dict:
    """获取版本信息"""
    info = {
        "branch": "unknown",
        "commit": "unknown",
        "message": "unknown",
        "dirty": False,
        "dirty_files": [],
        "pyproject_version": "unknown",
    }

    # 获取当前分支
    code, stdout, stderr = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0:
        info["branch"] = stdout

    # 获取最新 commit hash
    code, stdout, stderr = run_git_command(["rev-parse", "--short", "HEAD"])
    if code == 0:
        info["commit"] = stdout

    # 获取最新提交信息
    code, stdout, stderr = run_git_command(["log", "-1", "--format=%s"])
    if code == 0:
        info["message"] = stdout

    # 检查是否有未提交的改动
    code, stdout, stderr = run_git_command(["status", "--porcelain"])
    if code == 0:
        if stdout:
            info["dirty"] = True
            info["dirty_files"] = [line.strip() for line in stdout.split("\n") if line.strip()]

    # 读取 pyproject.toml 版本
    pyproject_path = config.version_manager_project_root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            import tomllib

            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                info["pyproject_version"] = data.get("project", {}).get("version", "unknown")
        except Exception:
            pass

    return info


async def check_file_changes(file_pattern: str) -> tuple[bool, list[str]]:
    """检查指定文件是否有改动

    Args:
        file_pattern: 文件路径模式，如 "poetry.lock" 或 "migrations/versions/"

    Returns:
        (是否有改动, 改动文件列表)
    """
    code, stdout, stderr = run_git_command(["diff", "--name-only", "HEAD", "origin/HEAD", "--", file_pattern])

    changed_files = []
    if code == 0 and stdout:
        for line in stdout.split("\n"):
            line = line.strip()
            if line:
                changed_files.append(line)

    return len(changed_files) > 0, changed_files


async def check_poetry_lock_changes() -> tuple[bool, list[str]]:
    """检查 poetry.lock 是否有改动

    Returns:
        (是否有改动, 改动文件列表)
    """
    return await check_file_changes("poetry.lock")


async def check_migration_changes() -> tuple[bool, list[str]]:
    """检查是否有新的数据库迁移文件

    Returns:
        (是否有新迁移, 新迁移文件列表)
    """
    migrations_dir = config.version_manager_project_root / "migrations" / "versions"
    if not migrations_dir.exists():
        return False, []

    # 获取当前本地所有迁移文件
    local_files = set()
    for f in migrations_dir.iterdir():
        if f.suffix == ".py" and not f.name.startswith("__"):
            local_files.add(f.name)

    # 检查远程是否有新的迁移（通过 git diff 比较）
    has_changes, changed_files = await check_file_changes("migrations/versions/")

    new_migrations = []
    for line in changed_files:
        if line.startswith("migrations/versions/") and line.endswith(".py"):
            filename = Path(line).name
            if filename not in local_files:
                new_migrations.append(filename)

    return len(new_migrations) > 0, new_migrations


async def perform_upgrade(user_id: str) -> dict:
    """执行更新操作

    Returns:
        更新结果信息
    """
    result = {
        "success": False,
        "git_pull_output": "",
        "git_pull_error": "",
        "has_poetry_changes": False,
        "poetry_install_output": "",
        "poetry_install_error": "",
        "has_db_changes": False,
        "new_migrations": [],
        "db_upgrade_output": "",
        "db_upgrade_error": "",
        "restarted": False,
    }

    # 1. 执行 git pull
    code, stdout, stderr = run_git_command(["pull"])
    result["git_pull_output"] = stdout
    result["git_pull_error"] = stderr

    if code != 0:
        logger.error(f"Git pull failed: {stderr}")
        return result

    # 2. 检查 poetry.lock 是否有改动
    has_poetry_changes, poetry_files = await check_poetry_lock_changes()
    result["has_poetry_changes"] = has_poetry_changes

    # 3. 如果有 poetry.lock 改动且配置为自动安装依赖，执行 poetry install
    if has_poetry_changes and config.version_manager_auto_install_deps:
        logger.info("Detected poetry.lock changes, installing dependencies...")
        code, stdout, stderr = run_poetry_command(["install"])
        result["poetry_install_output"] = stdout
        result["poetry_install_error"] = stderr

        if code != 0:
            logger.error(f"Poetry install failed: {stderr}")
            # 依赖安装失败不阻止后续操作，但记录错误

    # 4. 检查是否有数据库改动
    has_db_changes, new_migrations = await check_migration_changes()
    result["has_db_changes"] = has_db_changes
    result["new_migrations"] = new_migrations

    # 5. 如果有数据库改动且配置为自动升级，执行数据库升级
    if has_db_changes and config.version_manager_auto_upgrade_db:
        logger.info(f"Detected {len(new_migrations)} new migration(s), upgrading database...")
        code, stdout, stderr = run_nb_command(["orm", "upgrade"])
        result["db_upgrade_output"] = stdout
        result["db_upgrade_error"] = stderr

        if code != 0:
            logger.error(f"Database upgrade failed: {stderr}")
            return result

    result["success"] = True

    # 6. 如果配置为自动重启，执行重启
    if config.version_manager_auto_restart:
        result["restarted"] = True
        # 延迟重启，让消息发送完成
        asyncio.create_task(delayed_restart())

    return result


async def delayed_restart(delay: float = 3.0):
    """延迟重启机器人

    注意：此函数仅退出当前进程，不启动新进程。
    请确保使用进程管理器（如 MCSM、systemd、PM2 等）来自动重启服务。
    """
    await asyncio.sleep(delay)
    logger.info("Sending SIGTERM to current process for restart...")

    # 给自己发送 SIGTERM 信号，让进程正常终止
    # 这样可以触发 NoneBot2 的信号处理程序，执行清理工作
    os.kill(os.getpid(), signal.SIGTERM)


@version_cmd.assign("show")
async def handle_version_show(user_id: str = get_user_id()) -> None:
    """处理 version show 命令"""
    info = await get_version_info()

    # 构建版本信息文本
    dirty_status = "有未提交改动" if info["dirty"] else "干净"
    dirty_files_text = ""
    if info["dirty"] and info["dirty_files"]:
        dirty_files_text = "\n未提交文件：\n" + "\n".join([f"  {f}" for f in info["dirty_files"][:10]])
        if len(info["dirty_files"]) > 10:
            dirty_files_text += f"\n  ... 还有 {len(info['dirty_files']) - 10} 个文件"

    message = await lang.text(
        "version.info", user_id, info["branch"], info["commit"], info["message"], dirty_status, dirty_files_text
    )

    await version_cmd.finish(message)


@version_cmd.assign("upgrade")
async def handle_version_upgrade(user_id: str = get_user_id()) -> None:
    """处理 version upgrade 命令"""
    # 首先发送开始更新消息
    await lang.send("upgrade.start", user_id)

    # 执行更新
    result = await perform_upgrade(user_id)

    if not result["success"]:
        error_msg = result["git_pull_error"] or "Git pull 失败"
        await lang.finish("upgrade.failed", user_id, error_msg)
        return

    # 构建成功消息
    poetry_info = ""
    if result["has_poetry_changes"]:
        if config.version_manager_auto_install_deps:
            poetry_info = "\n检测到依赖改动，已自动安装依赖。"
        else:
            poetry_info = "\n检测到依赖改动（未自动安装）。"

    db_info = ""
    if result["has_db_changes"]:
        if config.version_manager_auto_upgrade_db:
            db_info = f"\n检测到数据库改动，已自动升级：\n" + "\n".join([f"  + {m}" for m in result["new_migrations"]])
        else:
            db_info = f"\n检测到数据库改动（未自动升级）：\n" + "\n".join(
                [f"  ! {m}" for m in result["new_migrations"]]
            )

    restart_info = "\n正在重启..." if result["restarted"] else ""

    await lang.finish("upgrade.success", user_id, result["git_pull_output"], poetry_info, db_info, restart_info)


@version_cmd.handle()
async def handle_version_default(user_id: str = get_user_id()) -> None:
    """默认处理 version 命令（无子命令时显示帮助）"""
    await lang.finish("help", user_id)
