# LarkLang - 本地化

`nonebot_plugin_larklang` 是 Moonlark 中的本地化插件，用于处理多语言支持。

::: tip

"为了保证一致性，任何可以接入的地方都应该接入本地化。"

——xxtg666

:::

## 语言操作类 `LangHelper`

### `__init__`

```python
def __init__(self, name: str = "") -> None:
```

初始化一个 `LangHelper` 对象。

#### 参数

- `name`: 插件名，对应 LarkLang 三级键中的第一级，为空时将自动从插件名获取（为插件名去掉 `nonebot_plugin_` 前缀）。

#### 返回

`None`

#### 异常

- `nonebot_plugin_larklang.exceptions.InvalidPluginNameException`: 获取插件名失败，且 `name` 参数为空。

::: tip

`InvalidPluginNameException` 异常很少出现，一般来说不用处理，必要时手动传入 `name` 参数就可以了。

:::

### `text`

```python
async def text(self, key: str, user_id: str | int, *args, **kwargs) -> str:
```

获取指定键的本地化文本。

::: tip

YAML 支持多行字符串，尽量不要在代码中按行进行拆分或拼接。

:::

#### 参数

- `key`: 键名，为 `xxx2.xxx3` 格式的字符串。
- `user_id`: 触发事件用户的 ID，未知时可填 `-1`。
- `args` 和 `kwargs`: 会直接被解包入 `format` 函数中。

#### 返回

`str` - 经过本地化的文本。

### `is_key_exists`

```python
async def is_key_exists(self, key: str, user_id: str | int) -> bool:
```

检查当前语言库中是否能够获取指定键。

#### 参数

- `key`: 键名，为 `xxx2.xxx3` 格式的字符串。
- `user_id`: 用户 ID。

#### 返回

`bool` - 如果键存在则返回 `True`，否则返回 `False`。

### `send`

```python
async def send(self, key: str, user_id: str | int, *args, matcher: Matcher = Matcher(), at_sender: bool = True, reply_message: bool = False, **kwargs) -> None:
```

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

- `key`: 本地化键名，为 `xxx2.xxx3` 格式的字符串。
- `user_id`: 用户 ID。
- `matcher`: 对应事件的事件响应器。
- `at_sender`: 是否在消息的开头提及发送者。
- `reply_message`: 是否回复对应消息。
- `args` 和 `kwargs`: 参数会被解包到 `lang.text` 中。

#### 返回

`None`

#### 异常

与 `Matcher().send` 可能出现的异常相同（`ActionFailed` 或 `NetworkError`）。

### `finish`

```python
async def finish(self, key: str, user_id: str | int, *args, matcher: Matcher = Matcher(), at_sender: bool = True, reply_message: bool = False, **kwargs) -> None:
```

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

### `reply`

```python
async def reply(self, key: str, user_id: str | int, *args, **kwargs) -> None:
```

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

## 键

LarkLang 的键名结构由至少二级组成。第一级会被映射到具体的文件名上，如 `test` 对应 `src/lang/...(具体的语言)/test.yaml`，一般为插件名，不包含 `nonebot_plugin_` 前缀。

第二级开始是键的位置，使用 `.` 连接。

### 高级自定义

对于每个键，最常见的是直接使用字符串的缩略写法，以上文 `sha1.sha1` 为例，完整写法如下：

```yaml
sha1:
  sha1:
    text:
      - `消息文本的 SHA1 摘要为: {}`
    use_template: true
```

由此可见，一个键由一个包含 `text` 和 `use_template` 字段的 `dict` 组成。

- `text`: 具体的文本，每次获取时都将在所有项目中随机一个。
- `use_template`: 是否使用模板

### 模板键

模板键的三级键名为 `__template__`，对应二级键名下所有 `use_tempalte` 为 `True` 的键都会应用该模板。

应用模板操作在 `format` 之前，所有模板键的 `use_template` 选项将被忽略。

任何模板键都要包含一个 `{}` 占位符，对应文本将替换掉此占位符。

### 列表

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
