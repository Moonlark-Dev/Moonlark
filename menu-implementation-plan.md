# /menu 指令实现方案

## 概述
在 Moonlark 中添加一个分级的 `/menu` 指令，类似于 help 的扩展，显示分类菜单。

## 需要修改的文件

### 1. `src/plugins/nonebot_plugin_larkhelp/__main__.py` - 核心逻辑

#### a) 修改 `get_templates()` 函数 - 过滤 superuser 分类
在原有函数中，当遍历 `help_list` 构建 categories 时，跳过 `category == "superuser"` 的指令：
```python
async def get_templates(user_id: str) -> list[dict[str, Any]]:
    if not help_list:
        raise ValueError("No Command")
    sorted_help_list = sorted(list(help_list.items()), key=lambda x: x[0])
    commands = []
    for command in [await get_help_dict(name, user_id, data) for name, data in sorted_help_list]:
        if command["category"] == "superuser":
            continue  # ← 新增：跳过 superuser
        # ... 原有逻辑不变 ...
```

#### b) 新增 `get_menu_templates(user_id: str)` 函数
返回所有分类（包含 superuser），每个分类包含 id、name（本地化）、commands、count（指令数）。
```python
async def get_menu_templates(user_id: str) -> list[dict[str, Any]]:
    """获取菜单所需的所有分类数据，包括 superuser"""
    if not help_list:
        raise ValueError("No Command")
    sorted_help_list = sorted(list(help_list.items()), key=lambda x: x[0])
    categories: dict[str, dict] = {}
    for name, data in sorted_help_list:
        cat_id = data.category
        if cat_id not in categories:
            categories[cat_id] = {"id": cat_id, "commands": []}
        cmd_dict = await get_help_dict(name, user_id, data)
        categories[cat_id]["commands"].append(cmd_dict)
    
    result = []
    for cat_id, cat_data in categories.items():
        cat_data["name"] = await lang.text(f"list.category.{cat_id}", user_id)
        cat_data["count"] = len(cat_data["commands"])
        result.append(cat_data)
    return result
```

#### c) 新增 `get_random_command(user_id: str)` 函数
随机返回一个非 superuser 分类的指令：
```python
import random

async def get_random_command(user_id: str) -> dict:
    """随机指令（排除 superuser）"""
    non_super = {name: data for name, data in help_list.items() if data.category != "superuser"}
    if not non_super:
        raise ValueError("No non-superuser commands")
    name = random.choice(list(non_super.keys()))
    return await get_help_dict(name, user_id, non_super[name])
```

#### d) 新增 `get_category_commands(category_id: str, user_id: str)` 函数
获取指定分类的指令列表：
```python
async def get_category_commands(category_id: str, user_id: str) -> Optional[dict]:
    """获取指定分类的指令数据"""
    commands = []
    for name, data in sorted(help_list.items(), key=lambda x: x[0]):
        if data.category == category_id:
            commands.append(await get_help_dict(name, user_id, data))
    if not commands:
        return None
    return {
        "id": category_id,
        "name": await lang.text(f"list.category.{category_id}", user_id),
        "commands": commands,
        "count": len(commands),
    }
```

#### e) 新增 `/menu` 指令的渲染函数和命令处理器

```python
# --- Root menu render ---
@creator("menu.html.jinja")
async def render_menu(user_id: str) -> bytes:
    categories = await get_menu_templates(user_id)
    random_cmd = await get_random_command(user_id)
    return await render_template(
        "menu.html.jinja",
        await lang.text("menu.title", user_id),
        user_id,
        {
            "categories": categories,
            "random_command": random_cmd,
            "usage_text": await lang.text("menu.usage_text", user_id),
        },
        {},
        True,  # cache
        True,  # resize
    )

# --- Category detail render ---
@creator("menu_category.html.jinja")
async def render_menu_category(user_id: str) -> bytes:
    # This is a hack - we need to pass category data via a different mechanism
    # Actually, let's use a different approach: pass category data in the render
    pass

# Actually, for the category detail, we can't use @creator easily because
# the data depends on which category is being viewed.
# We'll skip caching for category detail views and use direct rendering.

# --- Menu command ---
menu_cmd = on_alconna(Alconna("menu", Args["category?", str]))

@menu_cmd.assign("category")
async def _(category: str, user_id: str = get_user_id()):
    cat_data = await get_category_commands(category, user_id)
    if cat_data is None:
        await lang.finish("menu.category_not_found", user_id, category)
    try:
        await menu_cmd.finish(
            UniMessage().image(
                raw=await render_template(
                    "menu_category.html.jinja",
                    cat_data["name"],
                    user_id,
                    cat_data,
                    {"usage_text": await lang.text("list.usage_text", user_id)},
                    False,  # no cache for category detail
                    True,   # resize
                ),
                name="image.png",
            )
        )
    except FinishedException:
        raise
    except Exception:
        logger.error(traceback.format_exc())
        await menu_cmd.finish(await lang.text("command.error", user_id))

@menu_cmd.assign("$main")
async def _(user_id: str = get_user_id()):
    try:
        await menu_cmd.finish(
            UniMessage().image(
                raw=await render_menu(user_id),
                name="image.png",
            )
        )
    except FinishedException:
        raise
    except Exception:
        logger.error(traceback.format_exc())
        await menu_cmd.finish(await lang.text("command.error", user_id))
```

**⚠️ 重要：** 上面 e) 部分的设计有一个问题——`@creator` 装饰器需要无参函数，但其回调由 cache 系统调用。对于 category detail 视图，我们不能用 `@creator`，因为数据依赖 category 参数。直接用 `render_template` + 无缓存渲染即可。

### 2. 新建 `src/templates/menu.html.jinja` - 根菜单模板

布局：
- 标题：Moonlark 在这里喵~！
- 分类列表（每个分类显示 id、本地化名称和指令数）
- 分隔线
- Menu category 用法提示
- 分隔线
- 随机指令（指令名 + 描述）

```html
{% extends base %}

{% block body %}
<div class="row">
    <div class="col-12">
        {% if not background_url.startswith("https://www.dmoe.cc") %}
        <p style="text-align:center;font-size:20px;color:#ff69b4;">ฅ^•ﻌ•^ฅ Moonlark 在这里喵~！</p>
        {% else %}
        <p style="text-align:center;font-size:20px;">ฅ^•ﻌ•^ฅ Moonlark 在这里喵~！</p>
        {% endif %}
    </div>
</div>
<hr>
<div class="row">
    <div class="col-12">
        {% for c in categories %}
        <div class="category-item" style="margin: 5px 0;">
            <span class="badge bg-secondary">{{ c.id }}</span>
            <span>{{ c.name }}</span>
            <span class="badge bg-info rounded-pill">{{ c.count }} 个指令</span>
        </div>
        {% endfor %}
    </div>
</div>
<hr>
<p>{{ text.menu_category_hint }}</p>
<hr>
<div class="row">
    <div class="col-12">
        <h5>{{ text.random_title }}</h5>
        <p><span class="badge bg-info">{{ random_command.name }}</span> {{ random_command.description }}</p>
    </div>
</div>
{% endblock body %}
```

Wait, the template needs the `text` dict passed. Let me adjust.

Actually, looking at how `render_template` works:
```python
async def render_template(name, title, user_id, templates, keys={}, cache=False, resize=False, ...):
    if keys:
        templates = templates | {"text": keys}
```

So `keys` becomes `templates["text"]`. The text dict contains the localized strings.

For the menu root template, I need to pass text keys:
```python
keys={
    "menu_category_hint": ...,  # "使用 menu <分类ID> 查看分类详情"
    "random_title": ...,        # "随机指令"
}
```

### 3. 新建 `src/templates/menu_category.html.jinja` - 分类详情模板

布局：
- 分类名称（主标题）
- 指令列表（badge 指令名 + 简介）
- 分隔线
- 详细介绍（该分类背后的解释/菜单本身的说明）
- 用法（数量）
- 用法列表

```html
{% extends base %}

{% block body %}
<div class="row">
    <div class="col-12">
        <h2>{{ main_title }}</h2>
        <hr>
        <ul>
            {% for command in commands %}
            <li>
                <span class="badge bg-info">{{ command.name }}</span> {{ command.description }}
            </li>
            {% endfor %}
        </ul>
    </div>
</div>
{% endblock body %}
```

Hmm wait, the main_title is set by render_template as the page title. The category name will be the page title.

Actually, looking at the base template:
```html
<h1 class="text-center text-style">{{ main_title }}</h1>
```

So `main_title` is already the category name for the category detail. And the body block can just show the command list.

For the root menu, `main_title` would be the menu title text.

Let me simplify.

### 4. 添加 `list.category.superuser: 管理员` 到翻译文件

`src/lang/zh_hans/larkhelp.yaml`:
```yaml
list:
  category:
    superuser: 管理员
    # ... 其他已有分类
```

`src/lang/en_us/larkhelp.yaml`:
```yaml
list:
  category:
    superuser: Admin
    # ... 其他已有分类
```

`src/lang/zh_tw/larkhelp.yaml`:
```yaml
list:
  category:
    superuser: 管理員
    # ... 其他已有分类
```

### 5. 添加 menu 相关翻译键

`src/lang/zh_hans/larkhelp.yaml`:
```yaml
menu:
  title: Moonlark 在这里喵~！
  menu_category_hint: '使用 {prefix}menu <分类ID> 查看分类详情'
  random_title: 随机指令
  category_not_found: 未找到分类 {category}
  usage1: menu (查看分类菜单)
  usage2: menu <分类ID> (查看指定分类的指令列表)
```

Add similar entries to zh_tw and en_us.

### 6. 修改 superuser 指令的 category

`src/plugins/nonebot_plugin_openai/help.yaml`:
```yaml
commands:
  model: help_model;4;superuser  # setting → superuser
```

这是一个示例。其他需要 superuser 权限的指令（如 `lang` 的管理功能）也按照需要修改。

### 7. 注册 menu 指令的 help.yaml

把 menu 指令本身注册到 `nonebot_plugin_larkhelp/help.yaml`：
```yaml
commands:
  help: help;2;tools
  menu: menu;2;tools  # 新增
```

## 模板的最终设计

### Root menu (`menu.html.jinja`)
```
extends base
title: "Moonlark 在这里喵~！"
body:
  - ฅ^•ﻌ•^ฅ Moonlark 在这里喵~！ (带可爱猫娘颜文字)
  - 分隔线
  - 分类列表：每个 item = [id badge] [本地名称] [指令数 badge]
  - 分隔线
  - 提示文本："使用 menu <分类ID> 查看分类详情"
  - 分隔线
  - 随机指令：[指令名 badge] 简介
```

### Category detail (`menu_category.html.jinja`)
```
extends base
title: "分类名称" (如 "实用工具")
body:
  - 指令列表：每个 li = [指令名 badge] 简介
```

## 注意事项

1. `@creator` 装饰器用于 cache 系统，其回调函数签名固定为 `(user_id: str) -> bytes`。Root menu 可以用 `@creator`，category detail 不能（因为数据依赖 category 参数）。
2. 模板中 `{{ base }}` 变量由 `render_template_to_text` 自动传入，对应主题文件路径。
3. `render_template` 函数的 `keys` 参数会被合并到 `templates` 的 `text` key 下。
4. 英文和繁体翻译要同步添加。

## 环境信息

- 项目路径: /tmp/Moonlark
- GitHub 仓库: https://github.com/Moonlark-Dev/Moonlark.git
- 需要从 `origin/main` 创建新分支
- 分支名: `feat/menu-command`
- Git: 需要设置 proxy（见 TOOLS.md）
- 创建 PR 时需要设置代理

## 具体步骤

1. 确保在项目根目录 `/tmp/Moonlark`
2. `git checkout origin/main -b feat/menu-command`（基于 main 创建分支）
3. 依次修改上述文件
4. `git add -A && git commit -m "feat: add /menu command with hierarchical help"`（或其他合适的 commit message）
5. `https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 git push origin feat/menu-command`
6. 通过 GitHub API 创建 PR（使用 gh 命令或 web_fetch）
