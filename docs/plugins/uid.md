# LarkUID

> Import 位置: `src.plugins.nonebot_plugins_larkuid.session`

## 说明

此插件用于从请求的 `Authorization` 头中获取用户信息。

> Moonlark 的 API 鉴泉中，`Authorization` 头的 Token 与用户是一一对应的。

## 定义

::: tip

以下所有函数都返回一个依赖注入对象。在无法读取 `Authorization` 头或解析失败时，将返回 401 错误。

:::

### `def get_user_id(default: Optional[str] = None) -> str`

获取请求的用户 ID。

#### 参数

- `default` (`Optional[str]`): 默认值，如果请求头中没有 `Authorization`，则返回此值。

#### 返回

`str` - 用户 ID。

### `def get_user_data(registered: bool = False) -> MoonlarkUser`

获取请求的用户数据。

#### 参数

- `registered` (`bool`): 是否只返回已注册的用户数据，如果为 `True`，未注册用户将返回 403 错误。

#### 返回

`MoonlarkUser` - 可操作用户数据。

## 使用

::: tip

除了仅用于本地化，我们更推荐使用 `get_user_data` 而不是 `get_user_id`。

:::

### 声明依赖

```python
from nonebot import require
require("nonebot_plugin_larkuid")
```

### 获取用户 ID 并返回

```python
from src.plugins.nonebot_plugin_larkuid.session import get_user_id

from nonebot import get_app
from fastapi import Request, FastAPI
from typing import cast

app = cast(FastAPI, get_app())


@app.get("/api/users/current/id")
async def _(request: Request, user_id: str = get_user_id()) -> dict[str, str]:
    return {"user_id": user_id}
```

## 路由分配

- `/api`: 接口
- `/static`: 静态文件（保留）
