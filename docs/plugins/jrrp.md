# Jrrp

> Import 包名: `src.plugins.nonebot_plugin_jrrp.jrrp`

## 定义

### `def get_luck_value(user_id: str) -> int`

获取指定用户的幸运值。

#### 参数

- `user_id` (str): 用户 ID。

#### 返回

用户今日的人品值。

::: tip

对于所有人品值 `a`，`0 <= a <= 100`。

:::

## 使用

### 声明依赖

```python
from nonebot import require
require("nonebot_plugin_jrrp")
```

### 获取用户人品值

```python
from src.plugins.nonebot_plugin_jrrp.jrrp import get_luck_value
jrrp = get_luck_value("1234567890")
```
