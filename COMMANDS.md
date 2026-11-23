# Moonlark 指令列表

> 由 Moonlark & nonebot-plugin-larkhelp 生成
## `2048`: 2048 小游戏

数字合成游戏 —— 2048
- `/2048`
## `bingo`: 宾果游戏生成

输入大小与内容，一键生成宾果游戏图片
- `/bingo [列数] [行数] (开始创建宾果游戏)`
## `boothill`: 波提欧

模仿某被改造的联觉信标对文本进行过滤，仅支持简体中文。
- `/boothill <句子> (标准模式：仅替换拼音以 ma 开头的词)`
- `/boothill-fury <句子> (狂怒模式：替换所有触发词)`
## `buff`: 效果

查看当前附着的效果（Buff）列表与附着情况
- `/buff (查看当前附着的效果列表)`
- `/buff <效果ID> (查看指定效果的附着详情)`
## `chatterbox`: 群话痨排行

统计群聊中的话痨，需要在群聊中手动启用。QQ 官方节点仅支持查看排行，不支持功能开关。
- `/ct [total|7d|1d] (群话痨排行，默认总榜)`
- `/ct [total|7d|1d] --global (全局话痨排行)`
- `/ct -e|-d (功能开关)`
- `/ct [total|7d|1d] me|<@用户> (查询指定用户的话痨排行)`
## `consumables`: 消耗品

查看背包中的消耗品并使用，每次使用消耗一个
- `/consumables (查看消耗品列表)`
- `/consumables use <INDEX> [count] (使用消耗品)`
## `craft`: 合成机

把原料放进合成机并支付 VimCoin，等待一段时间后取走产物（会自动放入背包）。合成机可使用 VimCoin 升级，等级越高能同时进行的合成越多。
- `/craft (查看合成机、配方与进行中的合成)`
- `/craft start <配方ID> [数量] (开始合成)`
- `/craft collect (收取已完成的合成产物)`
- `/craft upgrade (升级合成机，等级 1-4 对应 2/4/6/10 个槽位)`
## `defuse-tnt`: 拆除 TNT

运气游戏——通过猜测排列出正确的拆除炸弹的密码。
- `/defuse-tnt`
## `epic-free`: Epic 免费游戏查询

查询 Epic Games Store 当前和即将到来的免费游戏。
- `/epic-free (查询免费游戏)`
## `equip`: 装备栏

查看装备的装备。装备激活后获得对应的被动效果，每一种类型的装备只能同时装备一件。
- `/equip (查看装备栏)`
- `/equip <背包序号> (装备背包中的装备)`
- `/equip off <类型> (卸下指定类型的装备)`
## `ftt`: 寻径指津

寻径指津玩法
- `/ftt (从随机地图开始)`
- `/ftt <seed> (从指定种子生成地图)`
- `/ftt legend (查看方块图例)`
## `has-or-not`: 有无有无

根据三组对照词猜出共同特征的小游戏。

题目给出三组同类型的对照词：「⭕ 有」一侧的三个词都具备某个共同特征，「❌ 无」一侧的三个词都不具备该特征。
对比三组词语推理出这个共同特征即可作答（答案不能直接照搬题面词语，表达同一特征的不同说法均算正确）。
每局最多可作答 10 次，猜中奖励 3 VimCoin；连续三分钟无任何消息时自动公布答案并结束本局。
- `/has-or-not (开始一局游戏)`
- `/has-or-not <答案> (作答)`
- `/has-or-not 查看答案 (查看答案并结束本局)`
- `/has-or-not 规则说明 (查看玩法规则)`
## `jrrp`: 今日人品

查询今天的人品值，今天也是幸运的一天～
- `/jrrp (获取今天的人品值)`
- `/jrrp r (今日幸运星[--rank])`
- `/jrrp rr (今日倒霉蛋[--rank-r])`
- `/jrrp reroll (重新计算今日人品值)`
- `/jrrp t (查看近 7 天人品走势)`
- `/jrrp t 7d (查看近 7 天人品走势)`
- `/jrrp t 30d (查看近 30 天人品走势)`
## `liang`: 查看当前是梁文峰还是梁文谷

查看当前是梁文峰还是梁文谷，以及距离切换还有多久。周六周日全天为梁文谷时段。
- `/liang (查看当前状态)`
## `market`: 跳蚤市场

玩家间物品交易市场：可以将背包中的物品上架出售，也可以购买其他玩家出售的物品。
所有交易收取 1% 手续费。
上架价格（第三个参数）留空时按该物品的平均成交价出售；填写连续的 + 或 - 可相对均价上浮或下调 1%（每多一个符号多 1%，最多 5%），例如 +++ 表示高于均价 3%；
也可以直接填写数字作为固定单价，用于还没有成交记录的物品。
- `/market (查看市场概况)`
- `/market list [页码] (浏览在售商品，每页 10 件)`
- `/market sell <背包编号> [数量] [价格] (上架物品，数量留空表示全部)`
- `/market buy <名称|编号> [数量] (购买物品)`
- `/market sell 3 5 +++ (将背包编号 3 的物品以高于均价 3% 的价格上架 5 个)`
## `minigame-rank`: 小游戏积分排名

查看 Moonlark 中游玩玩法的用户的排名
- `/minigame-rank`
## `missing-abbreviations`: 缩略

根据缩略词中被省略的部分，逆向猜出缩略词的文字推理小游戏。

每局抽走原词中构成缩略词的字或字母，只展示剩下部分作为题面。例如题面「林匹克动」来自「[奥]林匹克[运]动[会]」，正确答案是缩略词「奥运会」（不是原词全称；误填全称会提醒且不扣次数）。
卡关时可发送「提示」依次查看位置提示（用 ○ 标出缩略词的位置与字数）与领域提示，查看提示不扣次数也不减少奖励。
每局最多作答 10 次，猜中奖励 3 VimCoin；连续三分钟无消息将自动公布答案。支持别名「缩略」「ma」。

灵感来源：https://pqr.pkupuzzle.art/missing-abbreviations/
- `/missing-abbreviations (开始一局游戏)`
- `/missing-abbreviations <答案> (提交缩略词作答)`
- `/missing-abbreviations 提示 (查看下一条提示)`
- `/missing-abbreviations 查看答案 (公布答案并结束本局)`
- `/missing-abbreviations 规则说明 (查看玩法规则)`
## `quick-math`: 快速数学

以计算为核心的玩法。找到问题的答案，并在排行榜中获取更高的积分。（指令别名：qm）
- `/quick-math (查看主界面（玩法介绍、周积分排行、模式介绍）)`
- `/quick-math start [--level <等级>] (开始普通挑战)`
- `/quick-math pvp create [最大人数] (创建对战房间)`
- `/quick-math pvp join <房间码> (加入对战房间)`
- `/quick-math pvp start (开始对战（仅房主）)`
- `/quick-math pvp quit (退出对战房间)`
- `/quick-math zen <等级> (禅模式)`
- `/quick-math rank [--total] (积分排行榜)`
- `/quick-math points (查看总分详情)`
## `roll`: 掷骰子

消耗背包中的二十面骰子进行掷骰，点数越高奖励越多，掷出 1 还会倒扣 vi！
- `/roll (掷 1 个二十面骰子)`
- `/roll <count> (掷多个二十面骰子，并显示每个骰子的点数与总和)`
## `setu`: 随机图片

随机 Pixiv 插画
- `/setu (随机图片)`
- `/setu rank (查看使用排行)`
- `/setu-g <id> (查看缓存中的原图)`
## `sign`: 签到

每日签到，获取经验、VimCoin 和好感度奖励，连续签到可获得自动签到券
- `/sign (签到并查看签到结果)`
- `/sign auto (查看自动签到情况)`
- `/sign auto on|off (开启或关闭自动签到)`
- `/sign auto limit <数字> (重置自动签到券使用计数并设定可用张数，数字 <= 0 为不限制)`
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
## `sweet-potato`: 烫手山芋

群聊 2～8 人参与的联机小游戏。山芋会不断升温，持有者每回合都要决定传给谁、还是继续捂热，小心别在手里爆炸。
- `/sweet-potato info (查看烫手山芋的规则介绍)`
- `/sweet-potato rank (查看成功捂热次数排行)`
- `/sweet-potato create (在当前群聊创建房间)`
- `/sweet-potato join (加入当前会话的房间)`
- `/sweet-potato start (开始游戏，仅房主可用)`
- `/sweet-potato pass <序号|@玩家|random> (把山芋传给指定玩家)`
- `/sweet-potato hold (捂热山芋，重新抽取爆炸概率)`
- `/sweet-potato quit (退出房间；房主使用则解散房间，游戏中不可用)`
- `/sweet-potato restart (游戏结束后在当前房间再开一把)`
## `tol`: 关灯挑战

尝试关掉所有的灯_一盏灯被开启或关闭时它上、下、左、右边的灯的状态也会发生改变。
- `/tol`
## `trade`: 模拟股票市场

在 Moonlark 证券交易所低买高卖赚取 VimCoin 的模拟炒股玩法（全场共用同一只股票，无需填写股票代码）。

1. 开市时间：每天 08:00–24:00；其余时间休市，只能查看行情、不能买卖。
2. 股价变化：开市期间每 5 分钟自动波动一次，玩家买入也会推高股价、卖出会压低股价（K 线图红涨绿跌，固定展示最近若干根蜡烛，前一交易日的蜡烛以浅色显示）。
3. 日 K 历史：发送 trade history 查看按交易日聚合的日 K 线，影线与当日最高/最低价直接取自实际成交数据。
4. 隔夜跳空：每天 08:00 开市时会先跳空一次，跳空方向通常延续前一交易日尾盘的走势，幅度每天不同。
5. 隔日可卖：当天买入的股票会先冻结，第二天 08:00 开市后才能卖出。
6. 费用与限额：每次买卖各收 1% 手续费；每人每天最多买入 1000 股、卖出 1000 股。
7. 收益排行：发送 trade rank 查看总收益率排行榜，仍持有的股票按当前价格估值，未卖出也不会少算收益。

按比例或 all 买入时会自动预留手续费；QQ 用户可直接点击消息下方的按钮操作。
- `/trade (查看当前股价、K 线图与我的持仓)`
- `/trade buy <股数> (按股数买入，如填 100 买入 100 股)`
- `/trade buy <比例> (按余额比例买入，如填 50% 或 0.5 花一半余额买入)`
- `/trade buy all (用全部余额买入)`
- `/trade sell <股数> (按股数卖出，如填 100 卖出 100 股)`
- `/trade sell all (卖出当前全部可卖股票)`
- `/trade history (查看日 K 线历史，影线取自实际成交数据)`
- `/trade rank (查看总收益率排行榜)`
## `turtle-soup`: 海龟汤

AI 主持的「海龟汤」（情境猜谜）游戏。
系统会给出一个离奇的情境描述（汤面），你只能提出可以用「是 / 不是 / 不重要」回答的问题，
通过一步步提问推理出完整的故事真相（汤底）。群里所有人都可以提问，一局默认最多 50 个问题，
本局默认在 36 小时内都有效；期间 Moonlark 的闲聊会被暂时收起，专心当主持人。
- `/turtle-soup (开始一局海龟汤)`
- `/turtle-soup 〈问题〉 (向主持人提问)`
- `/turtle-soup progress (查看当前进度)`
- `/turtle-soup hint (获取一条提示)`
- `/turtle-soup recalculate (重新计算当前进度)`
- `/turtle-soup give-up (放弃本局并公布汤底)`
- `/turtle-soup rank (查看正确作答数排行)`
- `/turtle-soup help (查看玩法说明)`
## `wordle`: WORDLE

猜单词的游戏，支持多人游玩。

游玩提示：为了避免干扰使用，不成功的匹配不会被提示，也不能在一个会话中同时开启多个 WORDLE 游戏。
- `/wordle [长度=5]`
## `access`: 权限管理

Moonlark 权限控制 (仅 SUPERUSER 可用)
- `/access {ban|pardon} <主体ID> (封禁/解封用户)`
- `/access {block|unblock} <权限> <主体ID> (添加/移除权限)`
- `/access reload (重新加载权限表缓存)`
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
- `/bag usage <INDEX> / bag use <INDEX> (查看物品的使用指令，QQ 平台可点击按钮快速填入指令)`
## `gal-mode`: 私聊备选回复

开启后，私聊中的回复会延迟一条发送，并在每轮结束时附带 1~3 条备选回复按钮，点击按钮即可发送对应内容。该功能与私聊流式发送（chat stream，实验性）互斥。
- `/gal-mode on (开启私聊备选回复)`
- `/gal-mode off (关闭私聊备选回复)`
## `id`: 查询用户 ID

查看指定用户（或自己）的主账号 ID 和当前账号 ID
- `/id (查看自己的 ID)`
- `/id @用户 (查看指定用户的 ID)`
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
## `whoami`: 我是谁

查看用户帐号基本信息
- `/whoami (查看帐号信息)`
## `alias`: 指令别名

为常用指令设置个人专属的简短别名，之后发送 /别名 即可触发原指令
- `/alias (查看指令别名用法)`
- `/alias <原指令> <别名> (创建指令别名(别名需遵循变量命名规则))`
- `/alias rm <别名> (删除指定别名)`
- `/alias list (查看我的全部别名)`
## `bac`: 蔚蓝档案活动日历

查询蔚蓝档案现在和将来的卡池、活动信息，支持国服（默认）、国际服（参数：in）、日服（参数：jp）。
- `/bac (国服活动日历)`
- `/bac in|jp (国际/日服活动日历)`
## `bac-remind`: 总力战提醒管理

管理总力战/大决战提醒功能，开启后会在活动开始前1小时和结束前1小时发送提醒。仅支持 OneBot V11 协议。
- `/bac-remind (查看当前状态)`
- `/bac-remind on/off (开启/关闭提醒)`
## `bc`: 广播设置

开启或关闭所在群聊的广播接收，并查看最新更新公告
- `/bc (查看广播状态与最新更新公告)`
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
- `/指令排行 (查看近7天热门指令排行)`
- `/指令排行 <天数> (查看近N天热门指令排行(最大90天))`
## `command`: 指令用法查询

根据指令列表生成指定指令或功能的具体用法
- `/command <查询内容> (查询指令的具体用法)`
## `debate-helper`: 辩论助手

分析群聊中的争议或辩论，提供客观的双方观点摘要。
- `/debate [读取长度]`
## `github`: GitHub 链接解析

预览 GitHub 链接内容
- `/github <链接/仓库>`
## `grass`: 生草机

将输入文本进行同义词随机替换，生成搞笑的"生草"版本
- `/grass <文本> (对文本进行同义词随机替换(每次结果可能不同))`
- `/grass-fury <文本> (狂怒模式)`
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
## `sticker-dl`: 表情包下载

进入表情包下载模式后，发送表情包即可原样取回；QQ 表情/表情包暂不支持，会提示后继续等待；发送文字消息退出该模式。
- `/sticker-dl (进入表情包下载模式)`
## `summary`: 历史消息总结

使用 AI 总结群聊中的历史消息。读取长度默认为 200 条消息，最大为 270，需要在群聊中手动启用。
- `/summary [读取长度] (总结历史消息)`
- `/summary -s broadcast (广播风格总结)`
- `/summary -s topic (话题梳理)`
- `/summary -e|-d (功能开关)`
- `/summary --everyday-summary <on/off> (每日总结开关)`
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

回复一条消息，让 AI 结合上下文解释消息中的晦涩内容、专业术语、梗或缩写。在无法回复消息的平台上（如部分 QQ 适配器），也可以使用 /wdym N 指定指令之前的第 N 条消息。
- `/wdym (回复一条消息)`
- `/wdym N (指令消息记为 0，解释之前的第 N 条消息)`
## `word-cloud`: 群聊词云

根据群内最近的消息生成词云图片，时间范围默认为 24 小时，最大为 48 小时。需要先启用群消息总结功能。
- `/word-cloud [小时数]`
## `cave`: 回声洞

（与漂流瓶类似）投稿或查看其他用户投稿的回声洞，所有内容依照 CC-BY-NC-SA 4.0 许可协议授权
- `/cave (随机条目)`
- `/cave-a <内容...> (投稿条目)`
- `/cave-r [-c] <ID> (删除条目或评论)`
- `/cave-s <ID> (恢复 7 天内删除的条目)`
- `/cave-g <ID> (查看自己投稿的条目)`
- `/cave-s (统计投稿者)`
- `/cave-n <回复合并转发> (投稿合并转发消息)`
- `/cave-prompt (查看私聊图片投稿询问开关状态)`
- `/cave-prompt on|off (开启/关闭私聊图片投稿询问)`
## `chat`: 主动水群

基于 LLM 的主动水群功能，可以尝试用于活跃群气氛。（启用后将会收集、处理、并储存启用群聊的聊天记录和群员的昵称；在私聊中使用 chat on / chat off 可以开关私聊 Chat）在群聊中可通过 chat enhance 开关启用回复增强：开启后 Moonlark 发送的每条消息都会先按当前 Chat 提示词与最近对话重写一次（仅 OpenAI Provider 生效）。私聊中可用 chat stream 开启实验性的流式发送（默认关闭），回复会随模型输出逐字出现，与 gal-mode 互斥。
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
- `/chat compact [会话ID] (压缩消息队列，分析待定笔记后重置[SU])`
- `/chat mode [passionate|standard|silent] (查看或切换互动模式，切换将重置会话上下文)`
- `/chat reset <会话ID> (重置指定会话的所有历史消息并重置会话状态[SU])`
- `/chat review-all (对所有会话执行记忆整理并重置其消息队列[SU])`
- `/chat model [openai|gemini] [会话ID] (查看或设置模型 Provider，省略会话ID时设置全局默认[SU])`
- `/chat model default [会话ID] (恢复全局默认模型 Provider，带会话ID时该会话恢复跟随全局[SU])`
- `/chat enhance <on|off> (在群聊中开启或关闭回复增强)`
- `/chat stream <on|off> (在私聊中开启或关闭实验性流式发送，默认关闭，与 gal-mode 互斥)`
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
- `/email read all (将所有邮件标为已读)`
- `/email read <email_id> (将邮件标为已读)`
## `fav-rank`: 好感度排行

查看 Moonlark 好感度排行榜，展示所有用户的好感度排名。好感度通过日常互动累积，数值越高代表与 Moonlark 的亲密度越高。
- `/fav-rank (查看好感度排行榜)`
## `ghot`: 群发言热度

计算群聊消息的热度分数，并进行排名。使用此功能需要先使用 /summary -e 启用群历史消息总结功能，否则群热度分数恒为 0。
- `/ghot (查看群热度卡片：当前热度分数与排名、历史热度走势)`
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

查询 Moonlark 记录的群友在线时间段，以及某个时间点在线的概率
- `/online-timer [@用户]`
- `/online-timer rank (在线排行)`
## `rescue`: 救起倒地用户

花费 50 vi 救起一位倒地的用户，并选择费用由谁支付
- `/rescue @用户 (花费 50 vi 救起倒地用户，可选择费用由自己或对方支付)`
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
## `shop`: 商店

使用 VimCoin 购买礼物等商品，购买的物品会存入背包。
- `/shop (查看商品列表)`
- `/shop buy <编号> [数量] (购买商品)`
## `splat`: 砸鸡蛋

向指定用户丢鸡蛋造成伤害，查看被砸 / 丢鸡蛋排行榜和个人砸鸡蛋信息。
- `/splat eggs (查看各种鸡蛋的持有数量与效果)`
- `/splat switch <数字> (切换默认鸡蛋种类)`
- `/splat <@用户> [数量] [-t/--type <数字|英文id>] (向指定用户丢鸡蛋)`
- `/splat rank/throwers [7d|30d|total] (被砸 / 丢鸡蛋排行榜)`
- `/splat info [@用户] (查询砸鸡蛋信息)`
## `waifu`: 今日群老婆

匹配你的每日群老婆！（仅支持群聊使用）
- `/waifu (今日群老婆)`
- `/waifu divorce (离婚)`
- `/waifu force-marry <@群员> (强娶)`
## `wakeuprank`: 早起排行

在每日 4:00-14:00 间首次发消息记录早起时间，可进行早起次数排行、平均起床时间排行和今日起床时间轴。
- `/wakeuprank (早起次数排行)`
- `/wakeuprank avg (平均起床时间排行)`
- `/wakeuprank today (今日起床时间轴)`
## `bcsu`: 广播管理

发送和管理广播消息，可附加仅在 QQ 官方机器人上显示的自定义按钮
> 此指令仅 Moonlark 管理员可用。
- `/bcsu (查看广播管理菜单)`
- `/bcsu <内容> (设置广播内容)`
- `/bcsu clear (清除广播内容)`
- `/bcsu preview (预览广播内容)`
- `/bcsu submit (提交并发送广播)`
- `/bcsu button add <按钮名> <指令> (添加广播按钮，仅 QQ 官方机器人生效)`
- `/bcsu button remove <按钮名> (移除广播按钮)`
- `/bcsu button clear (清空全部广播按钮)`
- `/bcsu button list (查看当前广播按钮)`
## `gem-model`: Gemini 模型管理

管理 Gemini 模型配置（仅限超级用户）
> 此指令仅 Moonlark 管理员可用。
- `/gem-model (查看模型配置信息)`
- `/gem-model <模型名> (更换默认模型)`
- `/gem-model <模型名> <应用标识> (设置应用专用模型)`
- `/gem-model :default: <应用标识> (删除应用配置)`
## `md`: Markdown 渲染测试

将参数中的 Markdown 原样发送到当前群聊，用于测试 QQ 官方机器人的 Markdown 渲染效果（仅超管可用）
> 此指令仅 Moonlark 管理员可用。
- `/md <Markdown内容> (将 Markdown 原样发送到当前群聊测试渲染效果)`
## `model`: 模型管理

管理 OpenAI 模型配置（仅限超级用户）
> 此指令仅 Moonlark 管理员可用。
- `/model (查看模型配置信息)`
- `/model <模型名> (更换默认模型)`
- `/model <模型名> <应用标识> (设置应用专用模型)`
- `/model :default: <应用标识> (删除应用配置)`
## `subaccount`: 管理子账号

[管理员专用] 管理子账号绑定关系：查看绑定状态、绑定/解绑子账号
> 此指令仅 Moonlark 管理员可用。
- `/subaccount view <用户ID> (查看绑定状态)`
- `/subaccount bind <子账号ID> <主账号ID> (绑定子账号)`
- `/subaccount unbind <子账号ID> (解绑子账号)`
- `/subaccount unbind <主账号ID> --all (解绑全部子账号)`
## `version`: 版本管理

使用 git 和 nb_cli 管理版本，仅限 SUPERUSER
> 此指令仅 Moonlark 管理员可用。
- `/version show (显示版本信息)`
- `/version upgrade (更新代码)`
