# Email

`nonebot_plugin_email` 用于给用户发送邮件或获取用户的收件箱状态。

## 发送邮件 `send_email`

```python
async def send_email(
    receivers: list[str], subject: str, content: str, author: Optional[str] = None, items: list[EmailItemData] = []
) -> int:
```

向指定用户发送邮件。

### 参数

- `receivers`: 接收者用户ID列表
- `subject`: 邮件主题
- `content`: 邮件内容
- `author`: 邮件作者，默认为 `None`
- `items`: 邮件附件物品列表，默认为空列表

### 返回

`int` - 邮件ID

## 发送全局邮件 `send_global_email`

```python
async def send_global_email(
    subject: str, content: str, author: Optional[str] = None, items: list[EmailItemData] = []
) -> int:
```

向所有已注册用户发送全局邮件。

### 参数

- `subject`: 邮件主题
- `content`: 邮件内容
- `author`: 邮件作者，默认为 `None`
- `items`: 邮件附件物品列表，默认为空列表

### 返回

`int` - 邮件ID

## 邮件附件物品类型 `EmailItemData`

```python
class EmailItemData(TypedDict):
    item_id: str
    count: int
    data: dict[str, Any]
```

邮件附件物品的数据类型。

### 字段

- `item_id`: 物品ID
- `count`: 物品数量
- `data`: 物品数据

## 邮件数据类型 `DictEmailData`

```python
class DictEmailData(TypedDict):
    id: int
    author: str
    content: str
    subject: str
    time: datetime
    items: list[EmailItemData]
    is_read: bool
    is_claimed: bool
```

邮件数据的字典类型。

### 字段

- `id`: 邮件ID
- `author`: 邮件作者
- `content`: 邮件内容
- `subject`: 邮件主题
- `time`: 邮件发送时间
- `items`: 邮件附件物品列表
- `is_read`: 是否已读
- `is_claimed`: 是否已领取附件

## （生成器）获取未读邮件 `get_unread_email`

```python
async def get_unread_email(user_id: str) -> AsyncGenerator[DictEmailData, None]:
```

获取指定用户的未读邮件。

### 参数

- `user_id`: 用户ID

### 返回

`AsyncGenerator[DictEmailData, None]` - 未读邮件的异步生成器

## 获取未读邮件数 `get_unread_email_count`

```python
async def get_unread_email_count(user_id: str) -> int:
```

获取指定用户的未读邮件数量。

### 参数

- `user_id`: 用户ID

### 返回

`int` - 未读邮件数量
