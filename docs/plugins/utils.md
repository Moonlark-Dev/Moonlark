# LarkUtils

> Import 位置: `src.plugins.nonebot_plugin_larkutils`

## 依赖注入

::: tip

下列方法都使用了 NoneBot2 依赖注入功能，需要写在事件 Handler 的参数默认值中。

例如：

**获得 UserID**

```python
@matcher.handle()
async def _(user_id: str = get_user_id()) -> None:
    ...
```

**是否为 SuperUser 用户触发**

```python
@matcher.handle()
async def _(superuser: bool = is_user_superuser()) -> None:
    ...
```

:::

### `def get_group_id() -> str`

获取触发事件的群号。

### `def is_user_superuser() -> bool`

触发事件的用户是否为 SuperUser。

### `def get_user_id() -> str`

获取触发事件的用户 ID。

## 内容审核

### 类型定义

```python
from typing import TypedDict, Literal, Optional


class ReviewResult(TypedDict):      # 也就是一个字典
    
    # API 返回审核结果
    conclusion: Literal["合规", "疑似", "不合规", "出错"]
    
    # 审核失败原因
    message: Optional[str]
    
    # 审核是否通过
    compliance: bool
```

### 函数

#### `async def review_image(image: bytes) -> ReviewResult`

审核图片。

##### 参数

- `image` (bytes): 图片二进制数据。

##### 返回

审核结果。

#### `async def review_text(text: str) -> ReviewResult`

审核文本。

##### 参数

- `text` (str): 文本内容。

##### 返回

审核结果。

## 其他

### `async def get_id(session: async_scoped_session, col: ColumnExpressionArgument[int]) -> int`

::: danger

未经充分测试，不建议使用。

:::

获取 SQL 表新项目 ID

### `def get_galactic_time(earth_time: float) -> list[int]`

获取 GSC 时间。

#### 参数

- `earth_time` (float): 地球时间（Unix 时间戳）

#### 返回

包含 6 个项目的列表，分别为：

1. 标准年
2. 环月
3. 量日
4. 系统时
5. 分钟
6. 秒

## 帐号

### `async def get_main_account(user_id: str) -> str`

获取帐号的主帐号 ID（没有绑定时将返回传入的 `user_id`）。

#### 参数

- `user_id` (str): 用户 ID。

::: tip

Moonlark 允许用户进行多平台帐号绑定，所以拥有子帐号和主帐号设计。

子帐号和主帐号是每一个帐号的属性，没有绑定主帐号的帐号称为主帐号，绑定了主帐号的主帐号将变为子帐号。

在运行时子帐号需要转换为主帐号再对用户进行操作，不过在 `get_user_id` 和 `get_user` 函数都有类似处理。

:::
