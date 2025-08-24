# Moonlark 指令列表

> 由 Moonlark & nonebot-plugin-larkhelp 生成
## `bac`: 蔚蓝档案活动日历

查询蔚蓝档案现在和将来的卡池、活动信息，支持国服（默认）、国际服（参数：in）、日服（参数：jp）。

### 用法
- `/bac (国服活动日历)`
- `/bac in|jp (国际/日服活动日历)`
## `calc`: 计算器

通过 Wolfram|Alpha 计算表达式或回答问题

### 用法
- `/calc <问题> (询问 WolframAlpha)`
## `github`: GitHub 链接解析

预览 GitHub 链接内容

### 用法
- `/github <链接/仓库>`
## `holiday`: 剩余假期

查看剩余的假期

### 用法
- `/holiday`
## `hsrc`: 崩铁活动日历

《崩坏：星穹铁道》活动日历

### 用法
- `/hsrc`
## `int`: 进制转换器

转换进制

### 用法
- `/int <数字> [源进制(默认自动识别)] [目标进制(默认 10)]`
## `latex`: 渲染 LaTeX 表达式

将 LaTeX 表达式渲染为图片

### 用法
- `/latex <内容>`
## `luxun-said`: 鲁迅说没说

鲁迅到底说没说过？从鲁迅先生的作品中模糊搜索他的一句话。

### 用法
- `/luxun-said <内容>`
## `man`: 查询 Man

Linux 手册 (ManPage) 查询

### 用法
- `/man <名称> [章节] (查询 ManPage)`
## `motd`: MC 服务器查询

[lgc-NB2Dev/nonebot-plugin-picmcstat] 查询 Minecraft 服务器信息

### 用法
- `/motd <IP>`
## `pacman`: Linux 包搜索

搜索 Arch Linux 包

### 用法
- `/pacman <关键词>`
## `preview`: 预览网页

截图一个网页 (加载不完全请尝试指定 wait)

### 用法
- `/preview <URL> [-w|--wait <等待时间>] (截图URL)`
## `raw`: 生草机

基于翻译，一键生草（一种植物），仅支持中文。

### 用法
- `/raw <文本...>`
## `t`: 翻译器

翻译文本（默认英到中）

### 用法
- `/t <文本...> [-s|--sorce <源语言>] [-t|--target <目标语言>]`
## `time-progress`: 时间进度

查看本年/月/日的进度

### 用法
- `/time-progress`
## `boothill`: 波提欧

对句子进行一些？？？的处理，仅支持简体中文。

「他宝了个腿的。」 ——巡海游侠，波提欧


### 用法
- `/boothill <句子>`
## `setu`: 随机图片

随机 Pixiv 插画

### 用法
- `/setu (随机图片)`
- `/setu rank (查看使用排行)`
## `lang`: 本地化

Moonlark 本地化设置

### 用法
- `/lang (查看语言列表)`
- `/lang view <语言> (查看语言信息)`
- `/lang set <语言> (设置语言)`
- `/lang reload (重载语言[SU])`
## `status`: 系统状态

[lgc-NB2Dev/nonebot-plugin-picstatus] 获取 Moonlark 运行状态

### 用法
- `/status`
## `theme`: 主题

设定部分指令的图片渲染主题

### 用法
- `/theme (查看主题列表)`
- `/theme <name> (更换主题)`
## `online-timer`: 在线时间段

查询 Moonlark 记录的群友在线时间段

### 用法
- `/online-timer [@用户]`
## `waifu`: 今日群老婆

匹配你的每日群老婆！（仅支持群聊使用）

### 用法
- `/waifu (今日群老婆)`
- `/waifu divorce (离婚)`
- `/waifu force-marry <@群员> (强娶)`
