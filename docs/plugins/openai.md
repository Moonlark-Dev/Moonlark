# OpenAI

`nonebot_plugin_openai` 是 Moonlark 中负责与 LLM 交互的插件。

## 获得模型回复 `fetch_message`

```python
async def fetch_message(
    messages: Messages,
    use_default_message: bool = False,
    model: Optional[str] = None,
    functions: Optional[list[AsyncFunction]] = None,
    identify: Optional[str] = None,
    **kwargs,
) -> str:
```

获取模型的回复消息。

### 参数

- `messages`: 消息列表
- `use_default_message`: 是否使用默认消息，默认为 `False`
- `model`: 模型名称，默认为 `None`
- `functions`: 函数列表，默认为 `None`
- `identify`: 标识符，默认为 `None`
- `**kwargs`: 其他参数

### 返回

`str` - 模型的回复消息

## 生成一条消息 `generate_message`

```python
def generate_message(content: str | list, role: Literal["system", "user", "assistant"] = "system") -> Message:
```

生成一条消息。

### 参数

- `content`: 消息内容，可以是字符串或列表
- `role`: 消息角色，可以是 "system"、"user" 或 "assistant"，默认为 "system"

### 返回

`Message` - 生成的消息对象

## 回复获取类 `MessageFetcher`

```python
class MessageFetcher:
    def __init__(
        self,
        messages: Messages,
        use_default_message: bool = False,
        model: Optional[str] = None,
        functions: Optional[list[AsyncFunction]] = None,
        identify: Optional[str] = None,
        **kwargs,
    ) -> None:
    async def fetch_last_message(self) -> str:
    async def fetch_message_stream(self) -> AsyncGenerator[str, None]:
    def get_messages(self) -> Messages:
```

用于获取模型回复的类。

### 属性

- `messages`: 消息列表
- `use_default_message`: 是否使用默认消息
- `model`: 模型名称
- `functions`: 函数列表
- `identify`: 标识符

### 方法说明

- `__init__`: 初始化消息获取器
- `fetch_last_message`: 获取最后一条消息
- `fetch_message_stream`: 获取消息流
- `get_messages`: 获取消息列表