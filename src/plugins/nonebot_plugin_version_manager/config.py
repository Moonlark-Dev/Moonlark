from pydantic import BaseModel, Field
from nonebot import get_plugin_config
from pathlib import Path


class Config(BaseModel):
    """Version Manager Plugin Config"""

    version_manager_project_root: Path = Field(
        default=Path("."),
        description="项目根目录路径，包含 .git 和 migrations 的目录"
    )
    version_manager_git_path: str = Field(
        default="git",
        description="Git 可执行文件路径"
    )
    version_manager_nb_path: str = Field(
        default="nb",
        description="nb_cli 可执行文件路径"
    )
    version_manager_auto_install_deps: bool = Field(
        default=True,
        description="检测到 poetry.lock 改动时是否自动执行 poetry install"
    )
    version_manager_auto_upgrade_db: bool = Field(
        default=True,
        description="检测到数据库改动时是否自动升级"
    )
    version_manager_auto_restart: bool = Field(
        default=True,
        description="更新完成后是否自动重启"
    )


config = get_plugin_config(Config)
