# LarkHelp

`nonebot_plugin_larkhelp` 插件没有提供接口，所以本页面是关于帮助文件的编写方法。

## 帮助文件

指令帮助需要在插件文件夹下的 `help.yaml` 注册。

### 配置结构

- `plugin`: 本地化系统中的插件名 (一般来说是模块名去掉 `nonebot_plugin_` 前缀)
- `commands`: 命令列表
  - `<指令名1>`: 具体命令帮助（以下内容除 category 外全部为 `LarkLang.text` 的 `key` 参数）
    - `description`: 简介
    - `details`: 详细说明
    - `usages`: 用法列表（`list[str]`）
    - `category`: 分类，为 `game` `tools` `community` 或 `setting`

### 简便写法

命令的**具体命令帮助**还有一个简便的写法：

```yaml
<键名>;<用法数量>;分类
```

例如 `help;2;game` 相当于

```yaml
<COMMAND>:
  description: help.description
  details: help.details
  usages:
    - help.usage1
    - help.usage2
  category: game
```

### 用法格式

用法的基本格式如下：

```bash
指令名 <子命令> <args...> [options] (说明)
