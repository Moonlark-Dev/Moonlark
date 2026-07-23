# Moonlark 指令列表

> 由 Moonlark & nonebot-plugin-larkhelp 生成
## `2048`: 2048 小游戏

数字合成游戏 —— 2048
- `/2048`
## `bingo`: 宾果游戏生成

输入大小与内容，一键生成宾果游戏图片
- `/bingo [列数] [行数] (开始创建宾果游戏)`
## `boothill`: 波提欧

对句子进行一些？？？的处理，仅支持简体中文。

「他宝了个腿的。」 ——巡海游侠，波提欧

- `/boothill <句子>`
## `character`: 成员列表

（该功能仍在测试中）查看当前拥有的角色。
- `/character (查看角色列表)`
- `/character <index> (查看角色详情)`
## `chatterbox`: 群话痨排行

统计群聊中的话痨，该功能不支持 QQ 节点且需要在群聊中手动启用。
- `/ct (群话痨排行)`
- `/ct -e|-d (功能开关)`
- `/ct me|<@用户> (查询指定用户的话痨排行)`
## `defuse-tnt`: 拆除 TNT

运气游戏——通过猜测排列出正确的拆除炸弹的密码。
- `/defuse-tnt`
## `epic-free`: Epic 免费游戏查询

查询 Epic Games Store 当前和即将到来的免费游戏。
- `/epic-free (查询免费游戏)`
## `ftt`: 寻径指津

寻径指津玩法
- `/ftt (从随机地图开始)`
- `/ftt <seed> (从指定种子生成地图)`
- `/ftt legend (查看方块图例)`
## `jrrp`: 今日人品

查询今天的人品值，今天也是幸运的一天～
- `/jrrp (获取今天的人品值)`
- `/jrrp r (今日幸运星[--rank])`
- `/jrrp rr (今日倒霉蛋[--rank-r])`
- `/jrrp reroll (重新计算今日人品值)`
## `minigame-rank`: 小游戏积分排名

查看 Moonlark 中游玩玩法的用户的排名
- `/minigame-rank`
## `quick-math`: 快速数学

以计算为核心的玩法。找到问题的答案，并在排行榜中获取更高的积分。（指令别名：qm）
- `/quick-math [--level <开始的等级>] (开始挑战)`
- `/quick-math rank [--total] (积分排行榜)`
- `/quick-math points (查看总分详情)`
- `/quick-math zen <等级> (禅模式)`
## `sandbox`: 战斗沙箱

（该功能仍在测试中）启动战斗沙箱，进行模拟战斗。
- `/sandbox [标靶等级] [标靶数量]`
## `setu`: 随机图片

随机 Pixiv 插画
- `/setu (随机图片)`
- `/setu rank (查看使用排行)`
## `sudoku`: 数独解谜游戏

数独解谜游戏，提供不同难度级别的数独谜题。游戏可以错误检查功能，帮助用户学习数独技巧。
- `/sudoku new <num-holes> (生成指定空格数的数独)`
- `/sudoku change <row> <column> <value> (修改数独指定行列数字)`
- `/sudoku erase <row> <column> (去除数独指定行列数字)`
- `/sudoku hint (提供第一个空格的提示)`
- `/sudoku reset (重置数独为初始状态)`
- `/sudoku answer (展示答案)`
- `/sudoku undo (撤销操作)`
- `/sudoku redo (重做操作)`
## `team`: 设置战斗队伍

（该功能仍在测试中）设置战斗有关模块使用的队伍，配合 character 指令使用。
- `/team (查看当前队伍)`
- `/team set <位置> <index> (成员入队)`
## `tol`: 关灯挑战

尝试关掉所有的灯_一盏灯被开启或关闭时它上、下、左、右边的灯的状态也会发生改变。
- `/tol`
## `wordle`: WORDLE

猜单词的游戏，支持多人游玩。

游玩提示：为了避免干扰使用，不成功的匹配不会被提示，也不能在一个会话中同时开启多个 WORDLE 游戏。

- `/wordle [长度=5]`
## `access`: 权限管理

Moonlark 权限控制 (仅 SUPERUSER 可用)
- `/access {ban|pardon} <主体ID> (封禁/解封用户)`
- `/access {block|unblock} <权限> <主体ID> (添加/移除权限)`
## `bag`: 背包

查看，处理，使用背包中的物品
- `/bag (查看背包)`
- `/bag overflow list (查看 overflow 区物品列表)`
- `/bag overflow show <INDEX> (查看 overflow 区物品)`
- `/bag overflow get <INDEX> [count] (获取 overflow 区物品)`
- `/bag show <INDEX> (查看物品)`
- `/bag drop <INDEX> [count] (丢弃物品)`
- `/bag tidy (整理背包)`
- `/bag move <from> <to> (移动物品)`
- `/bag use <INDEX> [-c|--count <count>] (兼容旧物品使用入口，不支持礼物)`
## `lang`: 本地化

Moonlark 本地化设置
- `/lang (查看语言列表)`
- `/lang view <语言> (查看语言信息)`
- `/lang set <语言> (设置语言)`
- `/lang reload (重载语言[SU])`
## `panel`: 用户面板

查看用户数据面板
- `/panel (查看面板)`
## `present`: 赠送礼物

将背包中的礼物赠送给 Moonlark
- `/present <INDEX> [-c|--count <count>] (赠送礼物)`
## `private-chat-whitelist`: 私聊 Chat 白名单管理

管理可在私聊中使用 Chat 功能的用户白名单（仅限超级用户）
- `/private-chat-whitelist (查看白名单)`
- `/private-chat-whitelist add <用户ID> (添加用户)`
- `/private-chat-whitelist remove <用户ID> (移除用户)`
- `/private-chat-whitelist enable <用户ID> (启用)`
- `/private-chat-whitelist disable <用户ID> (禁用)`
## `setnick`: 修改昵称

修改自己在 Moonlark 中的昵称，不带参数则解锁昵称锁定
- `/setnick <昵称> (修改昵称，不带参数解锁锁定)`
## `status`: 系统状态

显示系统状态信息
- `/status`
## `theme`: 主题

设定部分指令的图片渲染主题
- `/theme (查看主题列表)`
- `/theme <name> (更换主题)`
## `version`: 版本管理

使用 git 和 nb_cli 管理版本，仅限 SUPERUSER
- `/version show (显示版本信息)`
- `/version upgrade (更新代码)`
## `whoami`: 我是谁

查看用户帐号基本信息
- `/whoami (查看帐号信息)`
## `bac`: 蔚蓝档案活动日历

查询蔚蓝档案现在和将来的卡池、活动信息，支持国服（默认）、国际服（参数：in）、日服（参数：jp）。
- `/bac (国服活动日历)`
- `/bac in|jp (国际/日服活动日历)`
## `bac-remind`: 总力战提醒管理

管理总力战/大决战提醒功能，开启后会在活动开始前1小时和结束前1小时发送提醒。仅支持 OneBot V11 协议。
- `/bac-remind (查看当前状态)`
- `/bac-remind on/off (开启/关闭提醒)`
## `bc`: 广播设置

开启或关闭所在群聊的广播接收
- `/bc (查看广播状态)`
- `/bc on (开启广播)`
- `/bc off (关闭广播)`
## `calc`: 计算器

通过 Wolfram|Alpha 计算表达式或回答问题
- `/calc <问题> (询问 WolframAlpha)`
## `check-history`: 发过了吗

检查最近 48 小时内是否已经讨论过某个话题或发送过某条消息。
- `/check-history [内容]`
- `/check-history (回复某条消息)`
## `cmd-rank`: 指令统计

统计指令使用情况，提供近N天热门指令排行
- `/指令排行 - 查看近7天热门指令排行`
- `/指令排行 <天数> - 查看近N天热门指令排行（最大90天）`
## `debate-helper`: 辩论助手

分析群聊中的争议或辩论，提供客观的双方观点摘要。
- `/debate [读取长度]`
## `github`: GitHub 链接解析

预览 GitHub 链接内容
- `/github <链接/仓库>`
## `group-daily`: 每日群聊总结

获取当日群聊的总结报告，需要先启用群消息总结功能。
- `/group-daily (获取当日群聊总结)`
## `help`: 命令帮助

获取命令用法
- `/help (获取命令列表)`
- `/help <命令名> (查看命令帮助)`
## `holiday`: 剩余假期

查看剩余的假期
- `/holiday`
## `hsrc`: 崩铁活动日历

《崩坏：星穹铁道》活动日历
- `/hsrc`
## `int`: 进制转换器

转换进制
- `/int <数字> [源进制(默认自动识别)] [目标进制(默认 10)]`
## `latex`: 渲染 LaTeX 表达式

将 LaTeX 表达式渲染为图片
- `/latex <内容>`
## `luxun-said`: 鲁迅说没说

鲁迅到底说没说过？从鲁迅先生的作品中模糊搜索他的一句话。
- `/luxun-said <内容>`
## `man`: 查询 Man

Linux 手册 (ManPage) 查询
- `/man <名称> [章节] (查询 ManPage)`
## `menu`: 分级菜单

显示分类菜单和随机指令
- `/menu (查看分类菜单)`
- `/menu <分类ID> (查看指定分类的指令列表)`
## `motd`: MC 服务器查询

[lgc-NB2Dev/nonebot-plugin-picmcstat] 查询 Minecraft 服务器信息
- `/motd <IP>`
## `pacman`: Linux 包搜索

搜索 Arch Linux 包
- `/pacman <关键词>`
## `preview`: 预览网页

截图一个网页 (加载不完全请尝试指定 wait)
- `/preview <URL> [-w|--wait <等待时间>] (截图URL)`
## `raw`: 生草机

基于翻译，一键生草（一种植物），仅支持中文。
- `/raw <文本...>`
## `summary`: 历史消息总结

使用 AI 总结群聊中的历史消息。读取长度默认为 200 条消息，最大为 270，该功能不支持 QQ 节点且需要在群聊中手动启用。
- `/summary [读取长度] (总结历史消息)`
- `/summary -s broadcast (广播风格总结)`
- `/summary -s topic (话题梳理)`
- `/summary -e|-d (功能开关)`
- `/summary --everyday-summary <on/off> (每日总结开关)`
## `t`: 翻译器

翻译文本（默认英到中）
- `/t <文本...> [-s|--sorce <源语言>] [-t|--target <目标语言>]`
## `time-progress`: 时间进度

查看本年/月/日的进度，支持年进度推送订阅
- `/time-progress - 查看时间进度
time-progress sub - 查看订阅状态
time-progress sub on/off - 开启/关闭年进度推送`
## `vote`: 投票

Moonlark 投票
- `/vote [-a|--all] (获取投票列表)`
- `/vote create [-g|--global] [-l|--last <持续(小时)>] [标题] (创建投票)`
- `/vote <投票ID> <选项编号> (参与投票)`
- `/vote <投票ID> (查看投票详情)`
- `/vote close <投票ID> (结束投票)`
## `wakatime`: WakaTime

在 Moonlark 上查看 WakaTime 时长并参与排行
- `/wakatime (查看我的 WakaTime 信息)`
- `/wakatime login (绑定 WakaTime 账户)`
- `/wakatime rank (查看 WakaTime 排行榜)`
## `wdym`: 请问什么意思

回复一条消息，让 AI 结合上下文解释消息中的晦涩内容、专业术语、梗或缩写。
- `/wdym (回复一条消息)`
## `cave`: 回声洞

（与漂流瓶类似）投稿或查看其他用户投稿的回声洞，所有内容依照 CC-BY-NC-SA 4.0 许可协议授权
- `/cave (随机条目)`
- `/cave-a <内容...> (投稿条目)`
- `/cave-r [-c] <ID> (删除条目或评论)`
- `/cave-s <ID> (恢复 7 天内删除的条目)`
- `/cave-g <ID> (查看自己投稿的条目)`
- `/cave-s (统计投稿者)`
- `/cave-n <回复合并转发> (投稿合并转发消息)`
## `chat`: 主动水群

基于 LLM 的主动水群功能，可以尝试用于活跃群气氛。（启用后将会收集、处理、并储存启用群聊的聊天记录和群员的昵称，仅支持非 QQ 官方节点）
- `/chat switch (切换功能启用状态)`
- `/chat on (启用功能)`
- `/chat off (禁用功能)`
- `/chat desire (查看触发概率信息)`
- `/chat mute (临时禁用水群功能 15 分钟)`
- `/chat unmute (取消临时禁用)`
- `/chat calls (查看最近的工具调用记录)`
- `/chat block user <add|remove|list> [用户ID] (管理屏蔽用户)`
- `/chat block keyword <add|remove|list> [关键词] (管理屏蔽关键词)`
- `/chat block list (查看所有屏蔽项)`
- `/chat ignore-mention <add|remove|list> [用户ID] (管理提及屏蔽用户)`
- `/chat reset (清除当前会话所有历史消息并重置会话状态)`
- `/chat stop (强制停止当前正在生成的响应)`
- `/chat stats (查看时间统计数据)`
- `/chat dropping <on|off> (开关礼物掉落功能)`
- `/chat compact [会话ID] (压缩消息队列，分析待定笔记后重置[SU])`
## `decision`: 虚假处分通知

根据群内最近 300 条消息，对指定群员生成一份符合公文格式的虚假处分通知（整活用）。
- `/decision @群友 <处分内容>`
## `email`: 邮件

进入 Moonlark 邮箱
- `/email (查看未读邮件)`
- `/email claim all (领取全部物品)`
- `/email claim <email_id> (领取指定邮件)`
- `/email unread all (将所有邮件标为未读)`
- `/email unread <email_id> (将邮件标为未读)`
## `fav-rank`: 好感度排行

查看 Moonlark 好感度排行榜，展示所有用户的好感度排名。好感度通过日常互动累积，数值越高代表与 Moonlark 的亲密度越高。
- `/fav-rank (查看好感度排行榜)`
## `ghot`: 群发言热度

计算群聊消息的热度分数，并进行排名。使用此功能需要先使用 /summary -e 启用群历史消息总结功能，否则群热度分数恒为 0。
- `/ghot (当前群聊热度分数)`
- `/ghot history [-l] (最近的天分数历史)`
## `lastseen`: 查询最后上线时间

记录并查询用户最后上线时间，支持全局和当前会话两种范围
- `/lastseen (查看自己最后上线时间)`
- `/lastseen @用户 (查看指定用户最后上线时间)`
- `/lastseen QQ号 (通过QQ号查询指定用户最后上线时间)`
## `logicfail`: 逻辑谬误生成器

随机跨领域因果关系谬误文案。（基于预先生成的文案，绝对没有使用大语言模型及人工智能！）
- `/logicfail`
## `neko-finder`: 找猫娘

根据近 2 天的消息对群友的“猫娘指数”进行打分。
- `/neko-finder`
## `online-timer`: 在线时间段

查询 Moonlark 记录的群友在线时间段
- `/online-timer [@用户]`
- `/online-timer rank (在线排行)`
## `rua`: 互动

通过 rua 指令与 Moonlark 进行亲密互动（如戳一戳、摸头、拥抱等）。不同的互动动作需要不同的好感度才能解锁。
- `/rua (使用当前选中的动作与 Moonlark 互动)`
- `/rua action (查看可用的互动动作列表)`
- `/rua action <编号> (切换当前使用的互动动作)`
- `/rua action <编号> --switch-only|-s (仅切换动作，不触发互动)`
- `/rua action <编号> --rua-only|-r (仅触发互动，不切换动作)`
- `/rua <编号> (使用指定动作与 Moonlark 互动)`
- `/rua rank (查看 rua 次数排行榜)`
## `schedule`: 每日任务

查看每日任务或领取每日任务奖励，每日刷新，部分功能仅在签到后可用。
- `/schedule (查看每日任务列表)`
- `/schedule collect (领取可领取的奖励)`
## `waifu`: 今日群老婆

匹配你的每日群老婆！（仅支持群聊使用）
- `/waifu (今日群老婆)`
- `/waifu divorce (离婚)`
- `/waifu force-marry <@群员> (强娶)`
## `wakeuprank`: 早起排行

在每日 4:00-14:00 间首次发消息记录早起时间，可进行早起次数排行、平均起床时间排行和今日排行。
- `/wakeuprank (早起次数排行)`
- `/wakeuprank avg (平均起床时间排行)`
- `/wakeuprank today (今日起床时间排行)`
## `ai-whitelist`: AI 白名单管理

管理 QQ 节点上允许使用 AI 功能的群聊白名单（仅限超级用户）
> 此指令仅 Moonlark 管理员可用。
- `/ai-whitelist (查看白名单)`
- `/ai-whitelist add <群号> (添加群聊到白名单)`
- `/ai-whitelist remove <群号> (从白名单移除群聊)`
- `/ai-whitelist enable <群号> (启用群聊 AI 功能)`
## `bcsu`: 广播管理

发送和管理广播消息
> 此指令仅 Moonlark 管理员可用。
- `/bcsu (查看广播管理菜单)`
- `/bcsu <内容> (设置广播内容)`
- `/bcsu clear (清除广播内容)`
- `/bcsu preview (预览广播内容)`
- `/bcsu submit (提交并发送广播)`
## `model`: 模型管理

管理 OpenAI 模型配置（仅限超级用户）
> 此指令仅 Moonlark 管理员可用。
- `/model (查看模型配置信息)`
- `/model <模型名> (更换默认模型)`
- `/model <模型名> <应用标识> (设置应用专用模型)`
- `/model :default: <应用标识> (删除应用配置)`
