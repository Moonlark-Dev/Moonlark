# Moonlark 指令列表

> 由 Moonlark & nonebot-plugin-larkhelp 生成
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
## `pcc`: 兑换猫爪币

将 PawCoin 兑换为 VimCoin

### 用法
- `/pcc [-b|--bag <index>] <count> (兑换)`
- `/pcc (查看汇率)`
## `theme`: 主题

设定部分指令的图片渲染主题

### 用法
- `/theme (查看主题列表)`
- `/theme <name> (更换主题)`
## `whoami`: 我是谁

查看用户帐号基本信息

### 用法
- `/whoami (查看帐号信息)`
## `bingo`: 宾果游戏生成

输入大小与内容，一键生成宾果游戏图片

### 用法
- `/bingo [列数] [行数] (开始创建宾果游戏)`
## `boothill`: 波提欧

对句子进行一些？？？的处理，仅支持简体中文。

「他宝了个腿的。」 ——巡海游侠，波提欧


### 用法
- `/boothill <句子>`
## `ftt`: 寻径指津

寻径指津玩法

### 用法
- `/ftt (从随机地图开始)`
- `/ftt <seed> (从指定种子生成地图，无奖励)`
- `/ftt exchange [count] (将积分兑换为 PawCoin)`
- `/ftt ranking (积分排名)`
- `/ftt points (查看积分)`
## `jrrp`: 今日人品

查询今天的人品值，今天也是幸运的一天～

### 用法
- `/jrrp (获取今天的人品值)`
- `/jrrp --rank (今日人品排名)`
- `/jrrp -g <分数> (计算下一个会出现某分数的日期)`
## `minigame`: 小游戏

查看小游戏积分、排名和小游戏列表

### 用法
- `/minigame (查看小游戏列表)`
- `/minigame rank (查看积分排行榜)`
- `/minigame me (查看积分)`
- `/minigame exchange [数量] (兑换PawCoin)`
## `quick-math`: 快速数学

以计算为核心的玩法。找到问题的答案，并在排行榜中获取更高的积分。

### 用法
- `/quick-math [-l|--level <开始的等级>] (开始挑战)`
- `/quick-math rank [{max|total}] (积分排行榜)`
- `/quick-math exchange [count] (使用总分兑换奖励)`
- `/quick-math points (查看总分详情)`
## `setu`: 随机图片

随机 Pixiv 插画

### 用法
- `/setu (随机图片)`
- `/setu rank (查看使用排行)`
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
## `schedule`: 每日任务

查看每日任务或领取每日任务奖励，每日刷新，部分功能仅在签到后可用。

### 用法
- `/schdeule (查看每日任务列表)`
- `/schdeule collect (领取可领取的奖励)`
## `status`: 系统状态

[lgc-NB2Dev/nonebot-plugin-picstatus] 获取 Moonlark 运行状态

### 用法
- `/status`
