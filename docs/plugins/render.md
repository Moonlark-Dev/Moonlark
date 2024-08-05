# Render

> Import 位置: `src.plugins.nonebot_plugin_render`


## 定义

### `async def render_template(name: str, title: str, user_id: str, templates: dict) -> bytes`

#### 参数

- `name` (str): 模板名称
- `title` (str): 标题
- `user_id` (str): 用户ID
- `templates` (dict): 模板变量

#### 返回

`bytes`: 渲染后的图片

## 模板编写

Render 读取的模板储存在 `src/templates` 中，后缀为 `*.jinja`。

一个模板的格式如下：

```html
{% extends base %}
{% block body %}
{{ content }}
{% endblock body %}
```

### 基模板

```html
{% extends base %}
```

这里使用了一个模板变量 `base` 作为基模板的名称，这个变量在渲染时会自动填充为对应主题的基模板。

### 内容块

#### `header`

拓展页面页面的头部。

#### `body`

卡片主体内容。

#### `card`

卡片。

::: warning

此块会覆盖 `body` 块。

:::

### 保留变量

::: danger

这些变量会在渲染时被自动填充，请避免使用这些模板变量名。

:::

- `base`: 主题基模板的相对路径。
- `main_title`: 页面主标题。
- `footer`: 页面页脚（版权信息）。

## 主题

Render 支持主题，主题基模板储存在 `src/templates/base` 中，主题列表储存在 `src/plugins/nonebot_plugin_render/themes.json` 中。

### 基模板

一个主题的基模板需要定义以下变量和内容块：

#### 模板变量

- `main_title`: 页面主标题。
- `footer`: 页面页脚（版权信息）。

#### 内容块

- `header`: 页面拓展头部。
- `body`: 卡片主体内容。
- `card`: 卡片。

::: tip

一般来说，`card` 会覆盖 `body` 块。

:::

### 主题配置

主题配置是一个 JSON 文件，格式为 `"主题ID": "主题模板相对于 src/templates 的路径"`。

## 本地化

所有向用户展示的文本都要被本地化。

## 本地文件引用

可以使用 `{% include "xx" %}` 块或 `src=xxx` 引入本地文件。 使用相对引入时，基路径为 `src/templates`。

## 使用

这是 Boothill 插件中渲染的代码：

```python
await render_template(
    "boothill.html.jinja",
    await lang.text("image.title", user_id),
    user_id,
    {
        "content": ...,
    },
)
```

`render_template` 函数会自动根据用户加载主题配置，并渲染模板。

::: tip

Render 插件的 Jinja2 配置会转义模板变量的所有 HTML 标记。

:::
