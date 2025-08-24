# LarkUser

> Import 位置: `src.plugins.nonebot_plugin_larkuser`

## 定义

### `class MoonlarkUser`

#### 方法

##### `def __init__(self, user_id: str) -> None`

> 此方法为 Python3 **魔法方法**

获取指定用户的 Moonlark User 对象。

###### 参数

- `user_id` (str): 用户 ID

##### `async def setup_user(self) -> None`

从数据库中更新用户数据。

##### `def get_nickname(self) -> str`

获取用户昵称。

##### `def is_main_account(self) -> bool`

用户是否为主帐号。

##### `def get_avatar(self) -> Optional[bytes]`

获取二进制用户头像。

##### `def get_base64_avatar(self) -> Optional[str]`

获取 Base64 编码的用户头像。

##### `def has_avatar(self) -> bool`

用户数据中是否有头像，为 False 时 `get_avatar` 和 `get_base64_avatar` 会返回 `None`。

##### `def get_fav(self) -> float`

获取好感度。

##### `def get_vimcoin(self) -> float`

获取用户拥有的 VimCoin 数量。

##### `def get_health(self) -> float`

获取用户血量。

##### `def get_gender(self) -> Optional[bool]`

获取用户性别。`True` 为男性，`False` 为女性，`None` 为用户未注册。

##### `def get_experience(self) -> int`

获取用户的经验值（总经验）。

##### `def get_register_time(self) -> Optional[datetime]`

获取用户注册时间，`None` 为未注册。

##### `def get_ship_code(self) -> Optional[str]`

获取用户舰船代号，`None` 为未注册。

##### `def get_level(self) -> int`

获取用户等级。

##### `def is_registered(self) -> bool`

用户是否注册。为 `False` 时 `get_register_time` `get_gender` `get_ship_code` 会返回 `None`。

##### `async def set_data(self, user_id: str, experience: Optional[int] = None, vimcoin: Optional[float] = None, health: Optional[float] = None, favorability: Optional[float] = None) -> None`

修改用户数据（对于大部分数据都有提供独立方法，避免使用此方法修改）。

##### `async def add_fav(self, count: float) -> None`

增加好感度。

##### `async def add_experience(self, count: int) -> None`

增加经验值。

##### `async def add_vimcoin(self, count: float) -> None`

增加 VimCoin 数量。

##### `async def use_vimcoin(self, count: float) -> None`

减少 VimCoin 数量。

::: warning

此方法不包含 VimCoin 余额检查，请自行检查余额。

:::

##### `async def has_vimcoin(self, count: float) -> bool`

检查 VimCoin 数量是否足够。

###### 参数

- `count`(int): 需要的数量。

#### 属性

::: warning

大部分属性都是只读的，请尽量使用方法读取或修改数据。

:::

- `user_id` (str): 用户 ID。
- `nickname` (str): 用户昵称。
- `register_time` (`Optional[datetime]`): 注册时间。
- `ship_code` (`Optional[str]`): 用户舰船代号。
- `gender` (`Optional[bool]`): 用户性别。
- `vimcoin` (float): VimCoin 数量。
- `experience` (int): 经验值。
- `health` (float): 血量。
- `fav` (float): 好感度。
- `avatar` (`Optional[bytes]`): 用户头像。
- `main_account` (bool): 用户帐号是否为主帐号。

### `async def get_user(user_id: str) -> MoonlarkUser`

获取 Moonlark 用户。

#### 参数

- `user_id` (str): 用户 ID。

#### 返回

可操作 Moonlark 用户类。

### `def patch_matcher(matcher: type[Matcher]) -> type[Matcher]`

将 Matcher 标记为 **仅已注册用户可用**。

::: tip

此方法会向传入的 Matcher 的 Handlers 列表的开头放入一个检查已注册用户的 Handler。 

:::

#### 参数

- `matcher` (`type[Matcher]`): 事件响应器。

#### 返回

传入的事件响应器。

### `def get_level_by_experience(exp: int) -> int`

通过总经验值计算等级。

#### 参数

- `exp` (int): 总经验值。

#### 返回

等级。

## 使用

### 声明依赖

```python
require("nonebot_plugin_larkuser")
```

### 获取用户

```python
from nonebot_plugin_larkuser import get_user

# 获取 ID 为 1234567890 的用户
user = await get_user("1234567890")
```

::: tip

此方法不会验证用户是否存在于 Moonlark 数据库中。
MoonlarkUser 对象依赖其中属性缓存，不要长时间占有一个 MoonlarkUser 对象，
以免其属性缓存与数据库不一致。

:::

### 获取用户数据

```python
import nonebot_plugin_larkuser.utils.register

nickname = nonebot_plugin_larkuser.utils.register.get_nickname()
level = user.get_level()
```

### 修改用户数据

```python
await user.add_vimcoin(114.514)
await user.add_experience(1919810)
```
