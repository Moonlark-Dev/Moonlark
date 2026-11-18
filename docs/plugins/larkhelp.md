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
```

## 帮助面板缓存与热门榜单刷新

`/help` 默认使用 Pillow 直接绘制帮助面板，版式不随 `nonebot_plugin_render` 的 `.theme` 变化，因此面板缓存由 `nonebot_plugin_larkhelp` 独立维护在 `localstore` 的 `nonebot-plugin-larkhelp` 缓存目录下（按语言各保存一份 `panel_<lang>.webp`，不再按 `语言 × 主题` 生成重复文件）：

- **启动预热**：在生命周期 `ready` 阶段（所有插件 `on_startup` 完成后）清空旧缓存，并在后台按语言预渲染面板。
- **热门指令榜单定时更新**：由 APScheduler 周期性（默认 30 分钟）检查近 7 天热门指令前三名与日期变化；仅在榜单或日期发生变动（或缓存缺失）时于后台重新绘制并原子替换磁盘缓存，保证 `/help` 始终直接命中缓存且热门榜单自动更新。

### 相关配置项

- `LARKHELP_CACHE`：是否启用帮助面板磁盘缓存与后台预热/定时刷新，默认 `true`。
- `LARKHELP_CACHE_REFRESH_INTERVAL`：后台检查热门指令榜单并刷新缓存的间隔（秒），默认 `1800`；设为 `<= 0` 时关闭定时刷新。

