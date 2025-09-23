# LarkUser

`nonebot_plugin_larkuser` 是 Moonlark 中的一个用户管理插件，用于管理用户的经验、等级、经济（VimCoin）等信息。

## 等待用户输入 `prompt`

```python
async def prompt(
    message: str | UniMessage,
    user_id: str,
    checker: Optional[Callable[[str], bool]] = None,
    retry: int = -1,
    timeout: int = 5 * 60,
    parser: Callable[[str], T] = lambda msg: msg,
    ignore_error_details: bool = True,
    allow_quit: bool = True,
) -> T:
```

等待用户输入，并对输入进行验证和解析。

### 参数

- `message`: 提示消息，可以是字符串或 UniMessage 对象。
- `user_id`: 用户 ID。
- `checker`: 输入验证函数，接受字符串参数，返回布尔值。如果为 None，则不进行验证。
- `retry`: 重试次数，-1 表示无限重试。
- `timeout`: 超时时间（秒）。
- `parser`: 输入解析函数，接受字符串参数，返回解析后的值。
- `ignore_error_details`: 是否忽略错误详情。
- `allow_quit`: 是否允许用户输入 "q" 退出。

### 返回

`T` - 解析后的用户输入。

## 获取用户信息 `get_user`

```python
async def get_user(user_id: str) -> MoonlarkUser:
```

获取 Moonlark 用户对象，根据用户是否注册返回不同类型的用户对象。

### 参数

- `user_id`: 用户 ID。

### 返回

`MoonlarkUser` - MoonlarkUser 对象。

## （生成器）获取已经注册的用户 `get_registered_users`

```python
async def get_registered_users() -> AsyncGenerator[MoonlarkRegisteredUser, None]:
```

异步生成器，用于获取所有已注册的用户。

### 返回

`AsyncGenerator[MoonlarkRegisteredUser, None]` - 已注册用户的异步生成器。

## 获取已经注册的用户列表 `get_registered_user_list`

```python
async def get_registered_user_list() -> list[MoonlarkRegisteredUser]:
```

获取所有已注册用户的列表。

### 返回

`list[MoonlarkRegisteredUser]` - 已注册用户的列表。

## 获取已注册用户的 ID 列表 `get_registered_user_ids`

```python
async def get_registered_user_ids() -> list[str]:
```

获取所有已注册用户的 ID 列表。

### 返回

`list[str]` - 已注册用户的 ID 列表。

## 换算经验总数为等级 `get_level_by_experience`

```python
def get_level_by_experience(exp: int) -> int:
```

根据用户的经验值计算用户等级。

### 参数

- `exp`: 用户的经验值。

### 返回

`int` - 用户等级。

## 将响应器设置为只允许已注册用户使用 `patch_matcher`

```python
def patch_matcher(matcher: type[Matcher]) -> type[Matcher]:
```

将响应器设置为只允许已注册用户使用。

### 参数

- `matcher`: 要修改的响应器类型。

### 返回

`type[Matcher]` - 修改后的响应器类型。

## 用户操作类 `MoonlarkUser`

```python
class MoonlarkUser(ABC):
    def __init__(self, user_id: str) -> None:
    async def setup_user(self) -> None:
    async def setup_user_id(self) -> None:
    def is_main_account(self) -> bool:
    def get_nickname(self) -> str:
    def has_nickname(self) -> bool:
    def get_avatar(self) -> Optional[bytes]:
    def get_base64_avatar(self) -> Optional[str]:
    def has_avatar(self) -> bool:
    def get_fav(self) -> float:
    def get_vimcoin(self) -> float:
    def get_health(self) -> float:
    def get_experience(self) -> int:
    def get_register_time(self) -> Optional[datetime]:
    def get_level(self) -> int:
    def is_registered(self) -> bool:
    async def set_data(
        self,
        user_id: str,
        experience: Optional[int] = None,
        vimcoin: Optional[float] = None,
        health: Optional[float] = None,
        favorability: Optional[float] = None,
        config: Optional[dict] = None,
    ) -> None:
    async def add_fav(self, count: float) -> None:
    async def add_experience(self, count: int) -> None:
    async def add_vimcoin(self, count: float) -> None:
    async def use_vimcoin(self, count: float, force: bool = False) -> bool:
    async def has_vimcoin(self, count: float) -> bool:
    def get_config_key(self, key: str, default: Optional[T] = None) -> T:
    async def set_config_key(self, key: str, value: Any) -> None:
```

Moonlark 用户操作基类，定义了用户相关的各种操作方法。

### 属性

- `user_id`: 用户 ID。
- `register_time`: 注册时间。
- `avatar`: 用户头像字节数据。
- `nickname`: 用户昵称。
- `vimcoin`: 用户的 VimCoin 数量。
- `experience`: 用户经验值。
- `health`: 用户健康值。
- `fav`: 用户好感度。
- `main_account`: 是否为主账号。
- `config`: 用户配置。

### 方法说明

- `__init__`: 初始化用户对象。
- `setup_user`: 设置用户信息。
- `setup_user_id`: 设置用户 ID。
- `is_main_account`: 检查是否为主账号。
- `get_nickname`: 获取用户昵称。
- `has_nickname`: 检查用户是否有昵称。
- `get_avatar`: 获取用户头像字节数据。
- `get_base64_avatar`: 获取用户头像的 Base64 编码。
- `has_avatar`: 检查用户是否有头像。
- `get_fav`: 获取用户好感度。
- `get_vimcoin`: 获取用户 VimCoin 数量。
- `get_health`: 获取用户健康值。
- `get_experience`: 获取用户经验值。
- `get_register_time`: 获取用户注册时间。
- `get_level`: 获取用户等级。
- `is_registered`: 检查用户是否已注册。
- `set_data`: 设置用户数据。
- `add_fav`: 增加用户好感度。
- `add_experience`: 增加用户经验值。
- `add_vimcoin`: 增加用户 VimCoin 数量。
- `use_vimcoin`: 使用用户 VimCoin。
- `has_vimcoin`: 检查用户是否有足够的 VimCoin。
- `get_config_key`: 获取用户配置项。
- `set_config_key`: 设置用户配置项。
