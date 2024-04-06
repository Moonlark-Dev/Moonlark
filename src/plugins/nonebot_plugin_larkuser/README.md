# nonebot-plugin-larkuser

Moonlark 用户信息插件

> [!TIP]
> 部分数据更新可能存在缓存

## 类型

```python
class UserData(Model):
    user_id: Mapped[str] = mapped_column(primary_key=True)
    nickname: Mapped[str]
    activation_time: Mapped[datetime]
    avatar: Mapped[bytes] = mapped_column(nullable=True, default=None)
    experience: Mapped[int] = mapped_column(default=0)
    vimcoin: Mapped[float] = mapped_column(default=0.0)
    health: Mapped[float] = mapped_column(default=100.0)
    favorability: Mapped[float] = mapped_column(default=0.0)
```

## 接口

### 等级相关

```python
def get_level_by_experience(exp: int) -> int
```

```python
async def add_exp(user_id: str, exp: int) -> None
```

### 用户相关

```python
async def get_user(user_id: str) -> UserData
```

```python
async def set_user_data(
    user_id: str,
    experience: Optional[int] = None,
    vimcoin: Optional[float] = None,
    health: Optional[float] = None,
    favorability: Optional[float] = None
) -> None
```

### 经济相关

```python
async def add_vimcoin(user_id: str, count: float) -> None
```

```python
async def use_vimcoin(user_id: str, count: float) -> None
```

```python
async def has_vimcoin(user_id: str, count: float) -> bool
```


