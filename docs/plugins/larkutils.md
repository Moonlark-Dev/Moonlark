# LarkUtils

`nonebot_plugin_larkutils` 是 Moonlark 中的一个底层插件，主要用于快速获取信息。

## （依赖注入）获取群号 `get_group_id`

```python
def get_group_id() -> Any:
```

使用 `nonebot_plugin_session` 插件获取群号，参数为：

```python
SessionId(id_type=SessionIdType.GROUP, include_bot_type=False, include_bot_id=False)
```

### 返回

`Any` - 依赖注入对象

## 审核图片 `review_image`

```python
async def review_image(image: bytes) -> ReviewResult:
```

审核图片内容。

### 参数

- `image`: 图片字节数据

### 返回

`ReviewResult` - 审核结果

## 审核文字 `review_text`

```python
async def review_text(text: str) -> ReviewResult:
```

审核文字内容。

### 参数

- `text`: 待审核的文字

### 返回

`ReviewResult` - 审核结果

## 审核结果类型 `ReviewResult`

```python
class ReviewResult(TypedDict):
    compliance: bool
    conclusion: str
    message: Optional[str]
```

审核结果类型定义。

### 字段

- `compliance`: 是否合规
- `conclusion`: 审核结论
- `message`: 审核消息

## 检查用户是否为超级用户 `is_superuser`

```python
async def is_superuser(event: Event, bot: Bot) -> bool:
```

检查当前用户是否为超级用户。

### 参数

- `event`: 事件对象
- `bot`: 机器人对象

### 返回

`bool` - 如果用户是超级用户则返回 `True`，否则返回 `False`

## （依赖注入）检查用户是否为超级用户 `is_user_superuser`

```python
def is_user_superuser() -> Any:
```

依赖注入版本的 `is_superuser` 函数，用于在命令处理函数中直接使用。

### 返回

`Any` - 依赖注入对象

## （依赖注入）获取用户 ID `get_user_id`

```python
def get_user_id() -> Any:
```

依赖注入版本的 `_get_user_id` 函数，用于在命令处理函数中直接使用。

### 返回

`Any` - 依赖注入对象

## （依赖注入）是否为私聊消息 `is_private_message`

```python
def is_private_message() -> bool:
```

依赖注入版本的 `private_message` 函数，用于在命令处理函数中直接使用。

### 返回

`bool` - 依赖注入对象

## （依赖注入）事件是否来自 QQ 机器人 `is_public_qq_bot`

```python
def is_public_qq_bot() -> Any:
```

依赖注入版本的 `_is_public_qq_bot` 函数，用于在命令处理函数中直接使用。

### 返回

`Any` - 依赖注入对象

## 获取账号的主账号 ID `get_main_account`

```python
async def get_main_account(user_id: str) -> str:
```

获取指定用户 ID 的主账号 ID。

### 参数

- `user_id`: 用户 ID

### 返回

`str` - 主账号 ID

## 设置账号的主账号 `set_main_account`

```python
async def set_main_account(user_id: str, main_account: str) -> None:
```

设置指定用户 ID 的主账号。

### 参数

- `user_id`: 用户 ID
- `main_account`: 主账号 ID

### 返回

`None`

## 解析特殊用户 ID `parse_special_user_id`

```python
def parse_special_user_id(user_id: str) -> dict[str, str]:
```

解析特殊用户 ID，返回包含解析结果的字典。

### 参数

- `user_id`: 特殊用户 ID

### 返回

`dict[str, str]` - 包含解析结果的字典

## 打开 Json 文件 `open_file`

```python
def open_file(file_name: str, file_type: FileType, default: T = {}, plugin_name: Optional[str] = None) -> FileManager:
```

打开一个 Json 文件，返回一个 `FileManager` 对象。

### 参数

- `file_name`: 文件名
- `file_type`: 文件类型
- `default`: 默认值，默认为 `{}`
- `plugin_name`: 插件名称，默认为 `None`

### 返回

`FileManager` - 文件管理器对象

## 文件类型枚举 `FileType`

```python
class FileType(Enum):
    DATA = "data"
    CACHE = "cache"
    CONFIG = "config"
```

文件类型枚举。

### 枚举值

- `DATA`: 数据文件
- `CACHE`: 缓存文件
- `CONFIG`: 配置文件

## 文件管理器 `FileManager`

```python
class FileManager:
    def __init__(self, path: Path, default: T) -> None:
    async def __aenter__(self) -> "FileManager":
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
    async def setup_file(self) -> None:
    async def save_file(self) -> None:
```

用于管理 Json 文件的类。

### 属性

- `path`: 文件路径
- `default`: 默认值

### 方法说明

- `__init__`: 初始化文件管理器
- `__aenter__`: 异步上下文管理器入口，用于加载文件内容
- `__aexit__`: 异步上下文管理器出口，用于保存文件内容
- `setup_file`: 加载文件内容
- `save_file`: 保存文件内容

## 获取用户的今日人品值 `get_luck_value`

```python
async def get_luck_value(user_id: str) -> int:
```

获取指定用户的今日人品值。

### 参数

- `user_id`: 用户 ID

### 返回

`int` - 用户今日的人品值，范围在 0-100 之间
