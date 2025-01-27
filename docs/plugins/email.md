# Email

> 部分不常用的用法此处不介绍，请参考源码中相关定义。

## 声明依赖

```python
from nonebot import require
require('nonebot_plugin_email')
```

## 发送邮件

> Import 位置： `src.plugins.nonebot_plugin_email.utils.send`。

### 定义

#### `async def send_email(receivers: list[str], subject: str, content: str, author: Optional[str] = None, items: list[EmailItemData] = []) -> int`

##### 参数

- `receivers` (`list[str]`): 收件人列表。
- `subject` (`str`): 邮件主题。
- `content` (`str`): 邮件内容。
- `author` (`Optional[str]`): 邮件作者 (一般不需要指定)。
- `items` (`list[EmailItemData]`): 邮件包含的物品列表。

##### 返回值

`int`: 邮件编号。

### 使用

以下是 QuickMath 插件中向用户发送邮件的代码:

```python
from nonebot_plugin_email.utils.send import send_email 
await send_email(
    
    # 收件人（只有一个）
    [user.user_id],
    
    # 邮件主题（即标题）
    await lang.text("award_email.subject", user.user_id),
    
    # 邮件内容（即正文）
    await lang.text("award_email.body", user.user_id, cycle["number"], point, rank, level),
    
    # 邮件附带物品（若干经验和猫爪币）
    items=[
        {"item_id": "moonlark:pawcoin", "count": award_pawcoin, "data": {}},
        {"item_id": "special:experience", "count": award_exp, "data": {}},
    ],
)
```

### 类型定义

```python
from typing import TypedDict, Any
class EmailItemData(TypedDict):
    item_id: str
    count: int
    data: dict[str, Any]
```

## 未读邮件

> Import 包名: `src.plugins.nonebot_plugin_email.utils.unread`

### 定义

#### `async def get_unread_email(user_id: str) -> AsyncGenerator[EmailData, None]`

获取用户未读邮件。

#### `async def get_unread_email_count(user_id: str) -> int`

获取用户的未读邮件数量。

### 类型定义

```python
from typing import TypedDict
from datetime import datetime

class EmailData(TypedDict):
    id: int
    author: str
    content: str
    subject: str
    time: datetime
    items: list[EmailItemData]
    is_read: bool
    is_claimed: bool

```
