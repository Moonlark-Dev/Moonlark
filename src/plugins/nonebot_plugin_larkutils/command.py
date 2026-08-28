from .config import config


def get_command_prefix() -> str:
    return config.command_start[0]