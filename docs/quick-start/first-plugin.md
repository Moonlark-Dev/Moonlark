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

### 1. 编辑插件入口文件

使用以上指令创建插件后，该插件入坑文件将位于 `src/plugins/nonebot_plugin_sha1/__init__.py`，这个文件目前只包含了插件元数据和其他信息，它应该是这样的：

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

我们进行如下更改：

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

这个插件不需要任何环境变量配置，我们将删除 `config.py` 文件。

### 2. 编写插件主体

在开始之前，我们需要引入一些必要的模块。

```python
import hashlib
from nonebot import require
from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg

require("nonebot_plugin_larklang")
require("nonebot_plugin_larkutils")

from nonebot_plugin_larklang import LangHelper
from nonebot_plugin_larkutils import get_user_id
```

然后，我们将为这个插件创建一个 `sha1` 指令，继续添加以下内容：

```python
# 如果插件的指令比较复杂，建议使用 on_alconna 而不是 on_command 进行匹配。 
sha1 = on_command("sha1")
lang = LangHelper()

@sha1.handle()
async def _(message: Message = CommandArg(), user_id: str = get_user_id()) -> None:
    text = message.extract_plain_text()
    sha1sum = hashlib.sha1(text.encode()).hexdigest()
    await lang.finish("sha1.sha1", user_id, sha1sum)
```

### 3. 创建本地化文件

在上一步中我们不难注意到，我们的 SHA1 插件使用了 `LarkLang` 对象中的一个 `finish` 方法向用户发送结果。我们需要为这个插件创建本地化文件，否则 `LarkLang` 插件永远也无法知道我们要向用户发送什么。

::: tip

Moonlark 代码内包含了多个语言的语言文件，在大多数情况下，我们只需要编辑 `src/lang/zh_hans` 下的内容。

:::


我们在 `src/lang/zh_hans` 下创建一个 `sha1.yaml`，然后写入以下内容： 

```yaml
sha1:
  sha1: '消息文本的 SHA1 摘要为: {}'
  # 这个就是键 `sha1.sha1`

help:
  description: SHA1 摘要计算
  details: 计算文本的 SHA1 摘要
  usage1: sha1 <内容>
```

同时，我们为这个文件额外写入了一个没有在代码中体现的 `help` 节，这个节将在下一步被用到。

::: tip

Moonlark 使用 LarkLang 实现本地化，也可以在 Moonlark 中添加相同语言的不同风格，任何向用户反馈的文本都要接入本地化。

:::

### 4. 创建指令帮助配置

在插件根目录，即 `src/plugins/nonebot_plugin_sha1` 下创建一个 `help.yaml`，LarkHelp 将在启动时读取这里面的内容并生成 `help` 指令展示的帮助列表：

```yaml
plugin: sha1
commands:
  sha1: help;1;tools
  # help 为本地化节名，1 为用法数量，tools 为指令分类
```

## 测试

```bash
poetry run nb run
```

出现以下输出说明插件加载成功：

```log
08-01 13:18:35 [SUCCESS] nonebot | Succeeded to load plugin "nonebot_plugin_sha1" from "src.plugins.nonebot_plugin_sha1"
```

此时，使用 `sha1 114514` 将会发送以下消息：

```
消息文本的 SHA1 摘要为: 2c8509df0df65f9826dc872a9acfea532c1f53c7
```

## 参考阅读

[发生了什么？][1]

[1]: what-happened


