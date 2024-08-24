# Help

> 此章节主要包含 LarkHelp 支持的插件帮助的编写方法，可以参考 [此文件][1] 阅读。

[1]: https://github.com/Moonlark-Dev/Moonlark/blob/main/src/plugins/nonebot_plugin_extrahelp/help.yaml

## 位置

帮助文件位于插件根目录的 `help.yaml` 文件。

## 结构

- `plugin`: 本地化插件名
- `commands`: 命令列表
  - `<指令名>`: 具体命令帮助
    - `description`: 简介
    - `details`: 详细说明
    - `usages`: 用法列表（`list[str]`）
  - ……

## 本地化

每个命令下的 `description`、`details`、`usages`(的内容) 都是本地化键名，为 `xxx2.xxx3` 的格式，二级键一般为 `help`。

## 用法编写规范

基本格式如下：

```bash
指令名 <subcommand> <args...> [options] (说明)
```

### 指令名

与对应的父键相同。

### 子命令

有多个子命令的指令应将每个子命令的用法拆分。

::: tip

假设 `hello` 指令下有 `x1` 和 `x2` 两个子指令（均没有参数），那么 `hello` 的用法应该拆分成如下两条：

1. `hello x1`
2. `hello x2`

:::

### 选择参数

除选项缩写外，选择参数应当使用花括号（`{...}`）包围，不同选项使用 `|` 分割。

::: warning

实际情况下，`{...}` 应当写成 `{{...}}`。

:::

::: tip

我们推荐将选择参数拆分成多个用法，并给予独立说明。

:::

### 必要参数

使用 `<...>` 包围，中间写参数说明。

### 可选参数

使用 `[...]` 包围，中间写参数说明

### 说明

用法的用途，在指令只有一个用法的情况下可不注明。

