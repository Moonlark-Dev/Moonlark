# LarkUID

`nonebot_plugin_larkuid` 提供了一些依赖注入函数，用于在 Fast API 请求响应器中根据 Authorization 头获取用户信息。

## 获取用户 ID `get_user_id`

```python
def get_user_id(default: Optional[str] = None) -> str:
```

根据请求中的 Authorization 头获取用户 ID。

### 参数

- `default`: 默认用户 ID，当无法从请求中获取用户 ID 时返回此值，默认为 `None`

### 返回

`str` - 依赖注入对象

## 获取用户数据 `get_user_data`

```python
def get_user_data(registered: bool = False) -> MoonlarkUser:
```

根据请求中的 Authorization 头获取用户数据。

### 参数

- `registered`: 是否要求用户已注册，默认为 `False`

### 返回

`MoonlarkUser` - 依赖注入对象
