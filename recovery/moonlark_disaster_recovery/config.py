from pydantic import BaseModel, Json, field_validator
import re
import json


class Config(BaseModel):
    port: int = 8080
    recovery_repl_user: str
    recovery_repl_password: str
    recovery_port: int
    recovery_database: str
    recovery_upstream_servers: Json[list[str]]
    recovery_local_backup_path: str
    sqlalchemy_database_url: str

    @field_validator("recovery_database", mode="before")
    @classmethod
    def extract_database_from_url(cls, v, info):
        # 如果已经设置了recovery_database，直接返回
        if v is not None:
            return v
        
        # 从sqlalchemy_database_url中提取数据库名
        if info.data and "sqlalchemy_database_url" in info.data:
            url = info.data["sqlalchemy_database_url"]
            # 匹配URL中的数据库名部分
            match = re.search(r"/([^/?]+)(?:\?.*)?$", url)
            if match:
                return match.group(1)
        
        # 如果无法提取，返回默认值或抛出异常
        raise ValueError("无法从sqlalchemy_database_url中提取数据库名")
    