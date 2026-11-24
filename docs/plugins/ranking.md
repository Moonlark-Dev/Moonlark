# Ranking

`nonebot_plugin_ranking` 用于在 Moonlark 中快速生成统一样式的排行榜。

## 生成图片 `generate_image`

```python
async def generate_image(ranked_data: list[RankingData], user_id: str, title: str, limit: int = 7) -> bytes:
```

生成排行榜图片。

### 参数

- `ranked_data`: 排序后的排行榜数据列表
- `user_id`: 用户 ID
- `title`: 排行榜标题
- `limit`: 显示的用户数量限制，默认为 7

### 返回

`bytes` - 生成的图片字节数据

## 接入新排行榜

排行榜图片与 Web 端共用同一份排序数据，接入时按以下步骤：

1. 插件中 `require("nonebot_plugin_ranking")`，并在 `__init__.py` 里导入注册 WebRanking 的模块。
2. 把数据整理成**已排序**的 `list[RankingData]`。
3. 指令侧调用 `generate_image()` 绘制统一风格的图片；QQ 官方用 `create_image_markdown` 发送，其它适配器直接发送图片，渲染失败时回退到文本。
4. 继承 `WebRanking` 并在模块导入时 `register()`，Web 端 `/api/rankings` 会自动发现，前端无需为本插件单独改代码。

```python
from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_ranking import RankingData, WebRanking, generate_image, register

lang = LangHelper()


class MyRanking(WebRanking):
    async def get_sorted_data(self, user_id: str) -> list[RankingData]:
        return await get_my_sorted_data()


register(MyRanking("my-plugin", "rank.web_name", lang))
```

`RankingData.data` 用于排序与默认展示；`display` 用于自定义展示值（如 `+50.00%`），`info` 是昵称下方的第二行说明。

## 历史数据与上线迁移

排行榜如果依赖累计数据（累计次数、累计收益等），上线前必须用数据库迁移回填旧数据；否则旧用户在新榜单里只有“新增部分”，排名会失真。

以 `nonebot_plugin_trade` 的收益排行榜为例：它用 `total_bought` / `total_sold` 计算总收益率，迁移时把旧持仓的 `cost_basis` 回填到 `total_bought`。这样排行上线后卖出旧仓时，卖出金额会和原持仓成本配对，不会出现“只加卖出值”导致收益率虚高。

无法从现有数据还原的历史（例如迁移前已经清仓、没有成交记录的用户）应在迁移说明和 PR 中写明排除规则，或等下一次交易后自然补齐。

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

### Web 响应中的 `data`

`/api/rankings/<id>` 返回的 `users[].data` 与 `me.data` 优先使用 `RankingData.display`（如果设置了），否则回退到 `data`。因此 Web 端可以直接展示返回值，不需要自己拼接单位；`RankingResponse` 里这两个字段的类型是 `int | float | str`。

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
    display: NotRequired[str]
```

排行榜单元数据类型。

### 字段

- `user_id`: 用户 ID
- `data`: 数据值（排序依据，也是默认展示值）
- `info`: 附加信息（昵称下方的第二行说明）
- `display`: 可选的自定义展示值，设置后覆盖 `data` 的展示（如 `+50.00%`）
