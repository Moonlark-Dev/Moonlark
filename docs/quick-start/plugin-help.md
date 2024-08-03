# 插件帮助

在编写 SHA1 插件时，我们还创建了一个文件，即 `help.yaml`。

## 这个文件有什么用？

此文件定义了此插件的帮助文本，使用 `help` 指令时会显示这些文本。

这个文件位于一个插件的根目录下，启动时会被 [LarkHelp][1] 插件读取。

## 文件内容与结构

```yaml
plugin: sha1
commands:
  sha1:
    description: help.description
    details: help.details
    usages:
      - help.usage
```

### `plugin`

> 类型: `str`

此键为帮助文本所在的键的第一级，所有帮助文本键的一级键名需要相同。

如果此键的值为 `sha1`，那么所有帮助文本键都要在 `sha1.yaml` 中。

与插件初始化 LangHelper 时的一级键相同是最常见的做法

::: tip

初始化 LangHelper() 时的第一个参数为一级键名，为 `None`（默认）时将获取插件名并去掉 `nonebot_plugin_` 前缀作为一级键名（这也是最常见的做法）。

:::

### `commands`

> 类型: `dict[str, dict[str, str | list[str]]]`

命令的具体帮助文本，键名一般为命令名。

::: tip

此键所有值的文本都为 LarkLang 键名，与 `LangHelper().text` 等函数传入格式相同（即不包含一级键的 `xxx2.xxx3`，二级键一般为 `help`）。

:::

#### `description`

> 类型: `str`

简介，在命令名右边显示。

#### `details`

> 类型: `str`

详细介绍，在命令名下方解释

#### `usages`

> 类型: `list[str]`

命令的所有用法及作用。


## 用法编写

命令用法使用符号表示信息，格式如下:


```bash
cmd subcmd A|B <arg> [option] (message)
```

- `cmd`: 命令名
- `subcmd`: 子命令名
- `A|B`: 在 A 或 B 中选择其一
- `<arg>`: 必要参数
- `[option]`: 可选参数
- `(message)`: 用法说明

::: tip

为了用法清晰，建议将选择参数拆分为多个用法，或仅在表示选项缩写时使用选择。

:::

## 测试插件帮助

```bash
help sha1
```

::: tip

修改 `help.yaml` 后需要重启！

:::

[1]: /plugins/help
