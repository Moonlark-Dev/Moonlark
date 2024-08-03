# 发生了什么？

::: tip

请结合 [上一章节][1] 的 SHA1 插件阅读本章节

:::

## 文件结构

创建插件后，Moonlark 的目录结构类似这样：

> 部分文件及目录已省略为 `...`

```bash
.
├── ...
└── src
    ├── lang
    │   ├── zh_hans
    │   │   ├── sha1.yaml
    │   └── ...
    ├── plugins
    │   ├── nonebot_plugin_sha1
    │   │   ├── __init__.py
    │   │   ├── __main__.py
    │   │   └── help.yaml
    │   └── ...
    └── templates
        └── ...
```

### `src/lang/`

此目录为 [LarkLang][2] 语言文件，每个目录为一个语言，默认语言（简体中文）为 `zh_hans`，`en_us` 和 `zh_tw` 使用 Crowdin 管理，不需要修改。

### `src/plugins/`

此目录为 Moonlark 插件目录，`nb-cli` 会从此目录加载插件

### `src/templates/`

此目录为 Jinja 模板文件，需要搭配 [Render][3] 插件使用。


## 插件做了什么

### `__init__.py`

#### 声明插件 [元数据][4]

```python
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-sha1",
    description="SHA1 摘要提取",
    usage="",
    config=None,
)
```

#### 声明插件依赖

```python
from nonebot import require

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")
```

向NoneBot2 声明此插件依赖 [LarkLang][2] 和 [LarkUtils][5] 插件

#### 导入 `__main__.py`

```python
from . import __main__
```

::: tip

我们习惯将大型插件的内部全局变量声明和指令注册单独写入 `__main__.py` 文件。

:::

### `__main__.py`

#### 导入依赖

```python
import hashlib
from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg

from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils import get_user_id
```

> 尽量避免使用通配符导入

#### 声明指令 [Matcher][6]

```python
sha1 = on_command("sha1")
```

向 NoneBot2 声明了一个 `sha1` 指令

#### 初始化 [LarkLang][2]

```python
lang = LangHelper()
```

LarkLang 会自动读取插件名并将该 LangHelper 文件对应到 `sha1.yaml`，此 LangHelper 对象仅能读取 `sha1.yaml` 的键。

在 LarkLang 中，插件名开头的 `nonebot_plugin_` 会被删除。

#### 声明响应器处理函数

```python
@sha1.handle()
async def _(message: Message = CommandArg(), user_id: str = get_user_id()) -> None:
    text = message.extract_plain_text()
    sha1sum = hashlib.sha1(text.encode()).hexdigest()
    await lang.finish("sha1.sha1", user_id, sha1sum)
```

> 我们将这个函数称为 Handler，所有 Handler 都是异步函数。


## 有关此 Handler 函数的参数

在这个函数中，使用 [NoneBot2 的依赖注入功能获取参数][7]。

### `message: Message = CommandArg()`

这个参数使用了 NoneBot2 内置的依赖注入函数，获取指令的参数。

假设用户在 QQ 使用了 `sha1 114514`，那么这个指令的参数是 `114514`，此时 `message` 参数的内容如下：

```python
Message("114514")
```

::: warning
此 Message 为 `nonebot.adapters.onebot.v11.Message`，非 `nonebot.adapters.Message`，具体类型会根据消息来源变化，但始终为 `nonebot.adapters.Message` 的子类
:::

### `user_id: str = get_user_id()`

`get_user_id()` 为 [LarkUtils][5] 提供的依赖注入函数，返回一个 `str`。

::: danger IMPORTANT
无论如何，请使用此函数获取触发事件主体的用户 ID。
:::

## 此 Handler 函数做了什么

我们假设，用户 ID 为 `1145141919810` 的用户使用了 `sha1 114514`。

此时，Handler 函数的参数值如下：

- `message`: `Message("114514")`
- `user_id`: `"1145141919810"`

### 获取消息纯文本

```python
text = message.extract_plain_text()
# text: "114514"
```

::: warning

使用 `extract_plain_text` 获取 `Message` 对象的纯文本，会丢掉所有非 `text` 消息段，我们建议使用 [Alconna][8] 插件来实现非 Text 参数消息段的有关功能。

:::

### 计算 SHA1 摘要并获取纯文本

```python
sha1sum = hashlib.sha1(text.encode()).hexdigest()
# sha1sum: "2c8509df0df65f9826dc872a9acfea532c1f53c7"
```

### 发送消息

```python
await lang.finish("sha1.sha1", user_id, sha1sum)
```

在这里，我们调用了 `lang.finish` 函数，由于 LangHelper 已绑定 `sha1.yaml`，LarkLang 会获取用户 `user_id: "1145141919810"` 的语言设置并在对应语言的 `sha1.yaml` 文件中查找 `sha1.sha1` 键的对应值，即 `"消息文本的 SHA1 摘要为: {}"`，随后使用 `format` 函数将剩下的变量 `sha1sum` 替换其中的 `{}` 值，替换后的文本为 `"消息文本的 SHA1 摘要为: 2c8509df0df65f9826dc872a9acfea532c1f53c7"`，随后这个文本会被发送并结束事件响应。

::: warning

`Langhelp().finish` 调用了 `Matcher().finish` 进行消息发送，会触发 `FinishedException` 并结束当前事件响应流程。

:::

::: tip

LarkLang 的键由三层组成，即 `xxx1.xxx2.xxx3`。

第一级为插件名，对应语言文件夹下的 `xxx1.yaml` 文件，会在 LangHelper 对象实例化时绑定。

在使用 `LangHelper().finish` 或其他有关函数的时候只需要传入后两级，即 `xxx2.xxx3`。

:::

## 下一步

[插件帮助][9]

[1]: first-plugin
[2]: /plugins/lang
[3]: /plugins/render
[4]: https://nonebot.dev/docs/advanced/plugin-info#%E6%8F%92%E4%BB%B6%E5%85%83%E6%95%B0%E6%8D%AE
[5]: /plugins/utils
[6]: https://nonebot.dev/docs/tutorial/matcher
[7]: https://nonebot.dev/docs/tutorial/event-data
[8]: https://github.com/nonebot/plugin-alconna
[9]: plugin-help
