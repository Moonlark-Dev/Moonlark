# Moonlark 指令列表

> 由 Moonlark & nonebot-plugin-larkhelp 生成
## `access`: 权限管理

Moonlark 权限控制 (仅 SUPERUSER 可用)

### 用法
- `/access {ban|pardon} <主体ID> (封禁/解封用户)`
- `/access {block|unblock} <权限> <主体ID> (添加/移除权限)`
## `lang`: 本地化

Moonlark 本地化设置

### 用法
- `/lang (查看语言列表)`
- `/lang view <语言> (查看语言信息)`
- `/lang set <语言> (设置语言)`
- `/lang reload (重载语言[SU])`
## `model`: 模型管理

管理 OpenAI 模型配置（仅限超级用户）

### 用法
- `/model (查看模型配置信息)`
- `/model <模型名> (更换默认模型)`
- `/model <模型名> <应用标识> (设置应用专用模型)`
- `/model :default: <应用标识> (删除应用配置)`
## `panel`: 用户面板

查看用户数据面板

### 用法
- `/panel (查看面板)`
## `status`: 系统状态

显示系统状态信息

### 用法
- `/status`
## `theme`: 主题

设定部分指令的图片渲染主题

### 用法
- `/theme (查看主题列表)`
- `/theme <name> (更换主题)`
## `version`: [缺失: version.help.description ((); {})]

[缺失: version.help.details ((); {})]

### 用法
- `/[缺失: version.help.usage_show ((); {})]`
- `/[缺失: version.help.usage_upgrade ((); {})]`
## `whoami`: 我是谁

查看用户帐号基本信息

### 用法
- `/whoami (查看帐号信息)`
## `bac`: 蔚蓝档案活动日历

查询蔚蓝档案现在和将来的卡池、活动信息，支持国服（默认）、国际服（参数：in）、日服（参数：jp）。

### 用法
- `/bac (国服活动日历)`
- `/bac in|jp (国际/日服活动日历)`
## `bac-remind`: 总力战提醒管理

管理总力战/大决战提醒功能，开启后会在活动开始前1小时和结束前1小时发送提醒。仅支持 OneBot V11 协议。

### 用法
- `/bac-remind (查看当前状态)`
- `/bac-remind on/off (开启/关闭提醒)`
## `calc`: 计算器

通过 Wolfram|Alpha 计算表达式或回答问题

### 用法
- `/calc <问题> (询问 WolframAlpha)`
## `check-history`: 发过了吗

检查最近 48 小时内是否已经讨论过某个话题或发送过某条消息。

### 用法
- `/check-history [内容]`
- `/check-history (回复某条消息)`
## `debate-helper`: 辩论助手

分析群聊中的争议或辩论，提供客观的双方观点摘要。

### 用法
- `/debate [读取长度]`
## `github`: GitHub 链接解析

预览 GitHub 链接内容

### 用法
- `/github <链接/仓库>`
## `help`: 命令帮助

获取命令用法

### 用法
- `/help (获取命令列表)`
- `/help <命令名> (查看命令帮助)`
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
## `summary`: 历史消息总结

使用 AI 总结群聊中的历史消息。读取长度默认为 200 条消息，最大为 270，该功能不支持 QQ 节点且需要在群聊中手动启用。

### 用法
- `/summary [读取长度] (总结历史消息)`
- `/summary -s broadcast (广播风格总结)`
- `/summary -s topic (话题梳理)`
- `/summary -e|-d (功能开关)`
- `/summary --everyday-summary <on/off> (每日总结开关)`
## `t`: 翻译器

翻译文本（默认英到中）

### 用法
- `/t <文本...> [-s|--sorce <源语言>] [-t|--target <目标语言>]`
## `time-progress`: 时间进度

查看本年/月/日的进度，支持年进度推送订阅

### 用法
- `/time-progress - 查看时间进度
time-progress sub - 查看订阅状态
time-progress sub on/off - 开启/关闭年进度推送`
## `vote`: 投票

Moonlark 投票

### 用法
- `/vote [-a|--all] (获取投票列表)`
- `/vote create [-g|--global] [-l|--last <持续(小时)>] [标题] (创建投票)`
- `/vote <投票ID> <选项编号> (参与投票)`
- `/vote <投票ID> (查看投票详情)`
- `/vote close <投票ID> (结束投票)`
## `wakatime`: WakaTime

在 Moonlark 上查看 WakaTime 时长并参与排行

### 用法
- `/wakatime (查看我的 WakaTime 信息)`
- `/wakatime login (绑定 WakaTime 账户)`
- `/wakatime rank (查看 WakaTime 排行榜)`
## `bingo`: 宾果游戏生成

输入大小与内容，一键生成宾果游戏图片

### 用法
- `/bingo [列数] [行数] (开始创建宾果游戏)`
## `boothill`: 波提欧

对句子进行一些？？？的处理，仅支持简体中文。

「他宝了个腿的。」 ——巡海游侠，波提欧


### 用法
- `/boothill <句子>`
## `character`: 成员列表

（该功能仍在测试中）查看当前拥有的角色。

### 用法
- `/character (查看角色列表)`
- `/character <index> (查看角色详情)`
## `chatterbox`: 群话痨排行

统计群聊中的话痨，该功能不支持 QQ 节点且需要在群聊中手动启用。

### 用法
- `/ct (群话痨排行)`
- `/ct -e|-d (功能开关)`
- `/ct me|<@用户> (查询指定用户的话痨排行)`
## `epic-free`: Epic 免费游戏查询

查询 Epic Games Store 当前和即将到来的免费游戏。

### 用法
- `/[缺失: epic_freegame.help.usage1 ((); {})]`
## `sandbox`: 战斗沙箱

（该功能仍在测试中）启动战斗沙箱，进行模拟战斗。

### 用法
- `/sandbox [标靶等级] [标靶数量]`
## `setu`: 随机图片

随机 Pixiv 插画

### 用法
- `/setu (随机图片)`
- `/setu rank (查看使用排行)`
## `team`: 设置战斗队伍

（该功能仍在测试中）设置战斗有关模块使用的队伍，配合 character 指令使用。

### 用法
- `/team (查看当前队伍)`
- `/team set <位置> <index> (成员入队)`
## `ghot`: 群发言热度

计算群聊消息的热度分数，并进行排名。使用此功能需要先使用 /summary -e 启用群历史消息总结功能，否则群热度分数恒为 0。

### 用法
- `/ghot (当前群聊热度分数)`
- `/ghot history [-l] (最近的天分数历史)`
## `lastseen`: 查询最后上线时间

记录并查询用户最后上线时间，支持全局和当前会话两种范围

### 用法
- `/[缺失: last_seen.lastseen (查看自己最后上线时间) ((); {})]`
- `/[缺失: last_seen.lastseen @用户 (查看指定用户最后上线时间) ((); {})]`
## `neko-finder`: 找猫娘

根据进 2 天的消息对群友的“猫娘指数”进行打分。

### 用法
- `/neko-finder`
## `online-timer`: 在线时间段

查询 Moonlark 记录的群友在线时间段

### 用法
- `/online-timer [@用户]`
- `/online-timer rank (在线排行)`
## `wtfis`: 这在说啥

随机跨领域因果关系谬误文案。（基于预先生成的文案，绝对没有使用大语言模型及人工智能！）

### 用法
- `/wtfis`
