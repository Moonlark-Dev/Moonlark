# Moonlark 指令列表

> 由 Moonlark & nonebot-plugin-larkhelp 生成
## `2048`: 2048 小游戏

数字合成游戏 —— 2048

### 用法
- `/2048`
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
## `defuse-tnt`: 拆除 TNT

运气游戏——通过猜测排列出正确的拆除炸弹的密码。

### 用法
- `/defuse-tnt`
## `ftt`: 寻径指津

寻径指津玩法

### 用法
- `/ftt (从随机地图开始)`
- `/ftt <seed> (从指定种子生成地图)`
## `jrrp`: 今日人品

查询今天的人品值，今天也是幸运的一天～

### 用法
- `/jrrp (获取今天的人品值)`
- `/jrrp r (今日幸运星[--rank])`
- `/jrrp rr (今日倒霉蛋[--rank-r])`
## `minigame`: 小游戏积分排名

查看 Moonlark 中游玩玩法的用户的排名

### 用法
- `/minigame-rank`
## `quick-math`: 快速数学

以计算为核心的玩法。找到问题的答案，并在排行榜中获取更高的积分。（指令别名：qm）

### 用法
- `/quick-math [--level <开始的等级>] (开始挑战)`
- `/quick-math rank [--total] (积分排行榜)`
- `/quick-math points (查看总分详情)`
- `/quick-math zen <等级> (禅模式)`
## `sandbox`: 战斗沙箱

（该功能仍在测试中）启动战斗沙箱，进行模拟战斗。

### 用法
- `/sandbox [标靶等级] [标靶数量]`
## `setu`: 随机图片

随机 Pixiv 插画

### 用法
- `/setu (随机图片)`
- `/setu rank (查看使用排行)`
## `sudoku`: 数独解谜游戏

数独解谜游戏，提供不同难度级别的数独谜题。游戏可以错误检查功能，帮助用户学习数独技巧。

### 用法
- `/sudoku new <num-holes> (生成指定空格数的数独)`
- `/sudoku change <row> <column> <value> (修改数独指定行列数字)`
- `/sudoku erase <row> <column> (去除数独指定行列数字)`
- `/sudoku hint (提供第一个空格的提示)`
- `/sudoku reset (重置数独为初始状态)`
- `/sudoku answer (展示答案)`
- `/sudoku undo (撤销操作)`
- `/sudoku redo (撤销操作)`
## `team`: 设置战斗队伍

（该功能仍在测试中）设置战斗有关模块使用的队伍，配合 character 指令使用。

### 用法
- `/team (查看当前队伍)`
- `/team set <位置> <index> (成员入队)`
## `tol`: 关灯挑战

尝试关掉所有的灯_一盏灯被开启或关闭时它上、下、左、右边的灯的状态也会发生改变。

### 用法
- `/tol`
## `wordle`: WORDLE

猜单词的游戏，支持多人游玩。

游玩提示：为了避免干扰使用，不成功的匹配不会被提示，也不能在一个会话中同时开启多个 WORDLE 游戏。


### 用法
- `/wordle [长度=5]`
## `access`: 权限管理

Moonlark 权限控制 (仅 SUPERUSER 可用)

### 用法
- `/access {ban|pardon} <主体ID> (封禁/解封用户)`
- `/access {block|unblock} <权限> <主体ID> (添加/移除权限)`
## `bag`: 背包

查看，处理，使用背包中的物品

### 用法
- `/bag (查看背包)`
- `/bag overflow list (查看 overflow 区物品列表)`
- `/bag overflow show <INDEX> (查看 overflow 区物品)`
- `/bag overflow get <INDEX> [count] (获取 overflow 区物品)`
- `/bag show <INDEX> (查看物品)`
- `/bag drop <INDEX> [count] (丢弃物品)`
- `/bag tidy (整理背包)`
- `/bag move <from> <to> (移动物品)`
- `/bag use <INDEX> [-c|--count <count>] [argv...] (使用物品)`
## `lang`: 本地化

Moonlark 本地化设置

### 用法
- `/lang (查看语言列表)`
- `/lang view <语言> (查看语言信息)`
- `/lang set <语言> (设置语言)`
- `/lang reload (重载语言[SU])`
## `panel`: 用户面板

查看用户数据面板

### 用法
- `/panel (查看面板)`
- `/panel i (查看邀请指令)`
## `status`: 系统状态

[lgc-NB2Dev/nonebot-plugin-picstatus] 获取 Moonlark 运行状态

### 用法
- `/status`
## `theme`: 主题

设定部分指令的图片渲染主题

### 用法
- `/theme (查看主题列表)`
- `/theme <name> (更换主题)`
## `whoami`: 我是谁

查看用户帐号基本信息

### 用法
- `/whoami (查看帐号信息)`
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
## `t`: 翻译器

翻译文本（默认英到中）

### 用法
- `/t <文本...> [-s|--sorce <源语言>] [-t|--target <目标语言>]`
## `time-progress`: 时间进度

查看本年/月/日的进度

### 用法
- `/time-progress`
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
## `cave`: 回声洞

（与漂流瓶类似）投稿或查看其他用户投稿的回声洞，所有内容依照 CC-BY-NC-SA 4.0 许可协议授权

### 用法
- `/cave (随机条目)`
- `/cave-a <内容...> (投稿条目)`
- `/cave-r [-c] <ID> (删除条目或评论)`
- `/cave-s <ID> (恢复 7 天内删除的条目)`
- `/cave-g <ID> (查看自己投稿的条目)`
- `/cave-c [-u|--user|--set <时间(分钟)>] (查看或修改冷却状态)`
- `/cave-s (统计投稿者)`
## `email`: 邮件

进入 Moonlark 邮箱

### 用法
- `/email (查看未读邮件)`
- `/email claim all (领取全部物品)`
- `/email claim <email_id> (领取指定邮件)`
- `/email unread all (将所有邮件标为未读)`
- `/email unread <email_id> (将邮件标为未读)`
## `online-timer`: 在线时间段

查询 Moonlark 记录的群友在线时间段

### 用法
- `/online-timer [@用户]`
## `schedule`: 每日任务

查看每日任务或领取每日任务奖励，每日刷新，部分功能仅在签到后可用。

### 用法
- `/schdeule (查看每日任务列表)`
- `/schdeule collect (领取可领取的奖励)`
## `waifu`: 今日群老婆

匹配你的每日群老婆！（仅支持群聊使用）

### 用法
- `/waifu (今日群老婆)`
- `/waifu divorce (离婚)`
- `/waifu force-marry <@群员> (强娶)`
