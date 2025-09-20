# Render

`nonebot_plugin_render` 用于将 src/templates 下的 jinja 模板渲染为图片。

::: tip 模板

Render 读取的模板储存在 `src/templates` 中，后缀为 `*.jinja`。

一个模板的格式如下：

```jinja
{% extends base %}
{% block body %}
{# Your content here #}
{% endblock body %}
```

| 内容块            | 位置                                 |
|-------------------|-------------------------------------|
| `header`         | 页面 `<header>` 末尾                  |
| `body`           |  `<div class="card-body">` 内部       |
| `card`           |  `<div class="card-body">` 外部，会覆盖 `body` 块 |

### 保留变量

- `base`: 主题基模板的相对路径。
- `main_title`: 页面主标题。
- `footer`: 页面页脚（版权信息）。
- `text`: 本地化文本。

:::

::: tip 主题

主题基模板储存在 `src/templates/base` 中，主题列表储存在 `src/plugins/nonebot_plugin_render/themes.json` 中。

主题配置是一个 JSON 文件，格式为 `"主题ID": "主题模板相对于 src/templates 的路径"`。

可以使用 `{% include "xx" %}` 块或 `src=xxx` 引入本地文件。 使用相对引入时，基路径为 `src/templates`。

:::

## 渲染模板 `render_template`

```python
async def render_template(
    name: str,
    title: str,
    user_id: str,
    templates: dict,
    keys: dict[str, str] = {},
    cache: bool = False,
    resize: bool = False,
) -> bytes:
```

渲染模板为图片。

### 参数

- `name`: 模板名称
- `title`: 页面标题
- `user_id`: 用户 ID
- `templates`: 模板参数字典
- `keys`: 本地化文本字典，默认为空字典
- `cache`: 是否使用缓存，默认为 `False`
- `resize`: 是否调整图片大小，默认为 `False`

### 返回

`bytes` - 渲染后的图片字节数据

## （修饰器）添加缓存创建函数 `creator`

```python
def creator(template_name: str):
```

添加缓存创建函数的修饰器。

### 参数

- `template_name`: 模板名称

### 返回

修饰器函数

## 生成本地化文本表 `generate_render_keys`

```python
async def generate_render_keys(helper: LangHelper, user_id: str, keys: list[str]) -> dict[str, str]:
```

生成本地化文本表。

### 参数

- `helper`: 本地化助手对象
- `user_id`: 用户 ID
- `keys`: 本地化键名列表

### 返回

`dict[str, str]` - 本地化文本字典