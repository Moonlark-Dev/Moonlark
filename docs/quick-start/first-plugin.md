# 第一个 Moonlark 插件

在此章节中，我们将创建一个获取用户输入使用并使用 SHA1 提取摘要并返回的插件，并结合该插件讲解 Moonlark 插件的编写。

## 创建插件

```bash
poetry run nb plugin create nonebot-plugin-sha1
```

```log
[?] 使用嵌套插件? N
[?] 请输入插件存储位置: src/plugins
```

## 编写插件

### `src/plugins/nonebot_plugin_sha1/__init__.py`

插件创建后，这个文件应该是这样的：

```python
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-sha1",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)
```

为了方便，我们进行如下更改：

```diff
- from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

- from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-sha1",
-   description="",
+   description="SHA1 摘要提取",
    usage="",
-   config=Config,
+   config=None,
)

- config = get_plugin_config(Config)

```

同时，删除 `config.py` 文件。

::: tip
这个插件不包含配置项，不应保留空的 `config.py` 文件
:::

```python
from nonebot.plugin import PluginMetadata
from nonebot import require

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-sha1",
    description="SHA1 摘要提取",
    usage="",
    config=None,
)


require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from . import __main__
```

### `src/plugins/nonebot_plugin_sha1/__main__.py` (新建)

```python
import hashlib
from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg

from ..nonebot_plugin_larklang import LangHelper
from ..nonebot_plugin_larkutils import get_user_id

sha1 = on_command("sha1")
lang = LangHelper()


@sha1.handle()
async def _(message: Message = CommandArg(), user_id: str = get_user_id()) -> None:
    text = message.extract_plain_text()
    sha1sum = hashlib.sha1(text.encode()).hexdigest()
    await lang.finish("sha1.sha1", user_id, sha1sum)
```

### `src/lang/zh_hans/sha1.yaml` (新建)

```yaml
sha1:
  sha1: '消息文本的 SHA1 摘要为: {}'
help:
  description: SHA1 摘要计算
  details: 计算文本的 SHA1 摘要
  usage: sha1 <内容>

```

::: tip

Moonlark 使用 LarkLang 实现本地化，也可以在 Moonlark 中添加相同语言的不通风格，任何向用户反馈的文本都要接入本地化。

:::

### `src/plugins/nonebot_plugin_sha1/help.yaml` (新建)

```yaml
plugin: sha1
commands:
  sha1:
    description: help.description
    details: help.details
    usages:
      - help.usage
```

## 测试

```bash
poetry run nb run
```

出现以下输出说明插件加载成功：

```log
08-01 13:18:35 [SUCCESS] nonebot | Succeeded to load plugin "nonebot_plugin_sha1" from "src.plugins.nonebot_plugin_sha1"
```

此时，使用 `sha1 114514` 将会出现以下消息：

```
消息文本的 SHA1 摘要为: 2c8509df0df65f9826dc872a9acfea532c1f53c7
```

## 下一步

[发生了什么？][1]

[1]: what-happened


