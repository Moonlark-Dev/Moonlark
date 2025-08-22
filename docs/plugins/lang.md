# LarkLang - 本地化

::: tip

“为了保证一致性，任何可以接入的地方都应该接入本地化。”

——xxtg666

:::

> Import 位置: `src.plugins.nonebot_plugin_larklang`


## 语言操作类 - `class LangHelper`

### `def __init__(self, name: str = "") -> None`

> 此方法为**魔法方法**

初始化一个 `LangHelper` 对象。

#### 参数

- `name`: 插件名，对应 LarkLang 三级键中的第一级，为空时将自动从插件名获取（为插件名去掉 `nonebot_plugin_` 前缀）。

#### 返回

`None`

#### 异常

- `src.plugins.nonebot_plugin_larklang.exceptions.InvalidPluginNameException`: 获取插件名失败，且 `name` 参数为空。

::: tip

`InvalidPluginNameException` 异常很少出现，一般来说不用处理，必要时手动传入 `name` 参数就可以了。

:::

### `async def text(self, key: str, user_id: str | int, *args, **kwargs) -> str`

获取指定键的本地化文本。

::: tip

YAML 支持多行字符串，尽量不要在代码中按行进行拆分或拼接。

:::

#### 参数

1. `key`: 键名，为 `xxx2.xxx3` 格式的字符串。
2. `user_id`: 触发事件用户的 ID，未知时可填 `-1`。

`args` 和 `kwargs` 会直接被解包入 `format` 函数中。

#### 返回

`str` - 经过本地化的文本。

### `async def is_key_exists(self, key: str, user_id: str | int) -> bool`

检查当前语言库中是否能够获取指定键。

### 参数

1. `key`: 键名，为 `xxx2.xxx3` 格式的字符串。
2. `user_id`: 用户 ID。

### `async def send(self, key: str, user_id: str | int, *args, matcher: Matcher = Matcher(), at_sender: bool = True, reply_message: bool = False, **kwargs) -> None`

向当前事件响应会话发送文本。


::: tip

假设 `matcher` 是一个 `Matcher`，`lang` 是一个 `LangHelper`，`user_id` 为一个用户 ID 字符串，那么此时：

```python
await matcher.send(await lang.text("aaa.bbb", user_id), at_sender=True)
```

和

```python
await lang.send("aaa.bbb", user_id)
```

等效。

:::

#### 参数

1. `key`: 本地化键名，为 `xxx2.xxx3` 格式的字符串。
2. `user_id`: 用户 ID。
3. `matcher`: 对应事件的事件响应器。
4. `at_sender`: 是否在消息的开头提及发送者。
5. `reply_message`: 是否回复对应消息。

`args` 和 `kwargs` 参数会被解包到 `lang.text` 中。

#### 返回

`None`

#### 异常

与 `Matcher().send` 可能出现的异常相同（`ActionFailed` 或 `NetworkError`）。

### `async def finish(self, key: str, user_id: str | int, *args, matcher: Matcher = Matcher(), at_sender: bool = True, reply_message: bool = False, **kwargs) -> None`

发送一条本地化消息并结束事件响应器。

::: tip

假设 `matcher` 是一个 `Matcher`，`lang` 是一个 `LangHelper`，`user_id` 为一个用户 ID 字符串，那么此时：

```python
await matcher.finish(await lang.text("aaa.bbb", user_id), at_sender=True)
```

和

```python
await lang.finish("aaa.bbb", user_id)
```

等效。

:::

::: warning

此方法会抛出 `FinishedException` 并结束当前事件响应。

:::


#### 参数

与 `LangHelper().send` 相同。

#### 返回

`None`

#### 异常

除 `Matcher().send` 可能出现的异常外，正常执行时将抛出 `FinishedException`。

### `async def reply(self, key: str, user_id: str | int, *args, **kwargs) -> None`

回复消息。

::: tip

假设 `lang` 为 `LangHelper`，`user_id` 为用户 ID，那么：

```python
await lang.send("xxx2.xxx3", user_id, reply_message=True, at_sender=False)
```

和

```python
await lang.reply()
```

等效。

:::

#### 参数

与 `LangHelper().text` 相同。

#### 返回

`None`

#### 异常

与 `LangHelper().send` 相同。


## 使用 `LangHelper`

在插件中使用以下方法初始化一个 `LangHelper`：

```python
from nonebot_plugin_larklang import LangHelper
lang = LangHelper()
```

假设插件名为 `nonebot_plugin_test`，此时 LangHelper 的一级键将被绑定为 `test`。

## 键

### 键名组成

LarkLang 的键名结构由三级组成。

#### 一级 - 插件名

此键会被映射到具体的文件名上，如 `test` 对应 `src/lang/...(具体的语言)/test.yaml`，一般为插件名，不包含 `nonebot_plugin_` 前缀。

#### 二级 - 场景

如指令名、`help` 或其他命名，对应 yaml 文件中的第一级。

#### 三级 - 具体键名

具体的键名，对应 yaml 文件中的第二级。


### 键名使用

一级键名会在 `LangHelper` 被实例化时直接绑定在该类上。

二级、三级一般组合书写出现在 `key` 参数中，使用 `.` 链接。

### 文件对应

语言键文件位于 `src/lang/(具体语言)/(一级键名).yaml`，是 yaml 文件，使用 yaml 格式。

这是我们在 [快速开始](../quick-start/first-plugin) 中创建的语言键文件，其一级键为 `sha1`，二三级键如下：

```yaml
sha1:

  # sha1.sha1
  sha1: '消息文本的 SHA1 摘要为: {}'


help:

  # help.description
  description: SHA1 摘要计算
  
  # help.details
  details: 计算文本的 SHA1 摘要

  # help.usage
  usage: sha1 <内容>
```

::: tip

如图所示的所有占位符都使用 Python3 中字符串的 `format` 方法进行替换。

:::

## 键的进阶写法

对于每个键，最常见的是直接使用字符串的缩略写法，以上文 `sha1.sha1` 为例，完整写法如下：

```yaml
sha1:
  sha1:
    text:
      - `消息文本的 SHA1 摘要为: {}`
    use_template: true
```

由此可见，一个键由一个包含 `text` 和 `use_template` 字段的 `dict` 组成。

### 字典键含义

- `text`: 具体的文本，每次获取时都将在所有项目中随机一个。
- `use_template`: 是否使用模板

### 模板键

模板键的三级键名为 `__template__`，对应二级键名下所有 `use_tempalte` 为 `True` 的键都会应用该模板。

应用模板操作在 `format` 之前，所有模板键的 `use_template` 选项将被忽略。

#### 写法

任何模板键都要包含一个 `{}` 占位符，对应文本将替换掉此占位符。

#### 示例

设置以下键：

```yaml
hello:
  __template__: 'so F**k you, {}!'
  name: nvidia       # 将应用模板
  name_1:            # 设置了 use_template 不会应用模板
    text: 
      - XiaoDeng3386
    use_template: false
names:
  name: xxtg666      # 不是同一个二级键名，不会应用模板
```

此时对应键的值如下：

- `hello.name`: so F\*\*k you，nvidia!
- `hello.name_1`: XiaoDeng3386
- `names.name`: xxtg666

### 列表写法

键还支持以下写法，相当于 `text` 选项：

```yaml
cat:
  meow:
    - 喵~
    - 喵！
```


## 语言配置文件

这是 `zh_hans` 的配置文件，位于 `src/lang/zh_hans/language.toml`:

```toml
[language]
version = 'latest'
author = 'Moonlark-Dev'

[display]
description="Moonlark 默认语言，简体中文"
```

通过指令 `lang view zh_hans` 我们可以很清晰地看到每个键的含义：

```txt
「语言详细信息」
名称: zh_hans
作者: Moonlark-Dev
版本: latest
Moonlark 默认语言，简体中文
```

::: tip

`language.toml` 有很多保留键，由于这些键名未实现或未测试，这里不做过多说明。

:::
