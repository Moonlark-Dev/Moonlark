class UserNotRegistered(Exception):
    pass


class UserNotWritable(Exception):
    """对只读的用户数据句柄执行写操作。

    用户数据通过 :func:`nonebot_plugin_larkuser.get_user` 读取，修改数值时必须在
    获取时显式声明写意图（``get_user(user_id, writable=True)``），否则可能基于过期快照
    覆盖其它协程刚写入的数据。
    """

    def __init__(self, user_id: str) -> None:
        super().__init__(f"用户 {user_id} 的数据句柄不可写，请使用 get_user(user_id, writable=True) 获取")
        self.user_id = user_id


class PromptTimeout(Exception):
    pass


class PromptRetryTooMuch(Exception):
    pass
