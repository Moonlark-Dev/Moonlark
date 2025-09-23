# Ranking

`nonebot_plugin_ranking` 用于在 Moonlark 中快速生成统一样式的排行榜。

## 生成图片 `generate_image`

```python
async def generate_image(ranked_data: list[RankingData], user_id: str, title: str, limit: int = 12) -> bytes:
```

生成排行榜图片。

### 参数

- `ranked_data`: 排序后的排行榜数据列表
- `user_id`: 用户 ID
- `title`: 排行榜标题
- `limit`: 显示的用户数量限制，默认为 12

### 返回

`bytes` - 生成的图片字节数据

## 可从 API 访问的排行榜类 `WebRanking`

```python
class WebRanking(ABC):
    def __init__(self, id_: str, name: str, lang_: LangHelper) -> None:
    def get_id(self) -> str:
    async def get_name(self, user_id: str) -> str:
    async def handle(
        self, request: Request, offset: int = 0, limit: int = 20, user_id: str = get_user_id("-1")
    ) -> RankingResponse:
    @abstractmethod
    async def get_sorted_data(self, user_id: str) -> list[RankingData]: ...
```

可从 API 访问的排行榜基类。

### 属性

- `ID`: 排行路径
- `NAME`: 排行名称（键名）
- `LANG`: 插件使用的 LangHelper 对象

### 方法说明

- `__init__`: 初始化 WebRanking 参数
- `get_id`: 获取排行路径
- `get_name`: 获取排行名称
- `handle`: 处理排行榜请求
- `get_sorted_data`: 抽象方法，获取排序后的数据

## API 可访问排行榜注册函数 `register`

```python
def register(rank: WebRanking) -> WebRanking:
```

注册排行榜。

### 参数

- `rank`: 排行榜对象

### 返回

`WebRanking` - 注册的排行榜对象

## 单元数据类型 `RankingData`

```python
class RankingData(TypedDict):
    user_id: str
    data: int | float
    info: str | None
```

排行榜单元数据类型。

### 字段

- `user_id`: 用户 ID
- `data`: 数据值
- `info`: 附加信息
