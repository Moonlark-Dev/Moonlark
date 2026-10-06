# nonebot_plugin_chat

基于 NoneBot2 的智能群聊插件，使机器人能够参与群聊并生成上下文感知的回复。

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                    Matcher (入口)                     │
│         接收消息/事件 → 分发到对应 Session             │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
   ┌─────────────┐          ┌──────────────┐
   │ GroupSession │          │PrivateSession│
   │   群聊会话    │          │   私聊会话    │
   └──────┬──────┘          └──────┬───────┘
          │                        │
          ▼                        ▼
   ┌──────────────────────────────────────┐
   │        MessageProcessor (核心)        │
   │  消息解析 → 上下文构建 → 回复生成      │
   └──────┬───────┬───────┬───────┬───────┘
          │       │       │       │
          ▼       ▼       ▼       ▼
     TokenBucket  ToolManager  AI Agent  StatusManager
      (流控)      (工具调用)   (自主推理)   (情绪状态)
```

## 核心组件

### MessageProcessor

消息处理核心，负责从消息队列中取出消息、解析、构建上下文并生成回复。

**关键职责：**
- 消息解析：`MessageParser` 处理 UniMessage，提取文本/图片/链接
- 上下文构建：`generate_additional_prompt` 注入用户画像、好感度、笔记、即时记忆、情绪状态
- 回复生成：调用 `MessageQueue.fetch_reply` 通过 OpenAI API 生成回复
- 工具调用：通过 `ToolManager` 管理可用工具（网页浏览、Wolfram Alpha、搜索引擎、B站解析、贴纸等）
- 即时记忆：每处理一定量消息后，调用 AI 从最近消息中提取即时记忆

### Chat Context（上下文管理）

会话上下文由 `core/context.py` 的 `ChatContext` 统一持有，`BaseSession` 与
`MessageQueue` 都不再自己保存消息。一个 `MessageQueue` 实例化一个 `ChatContext`。

- **存储**：`nonebot_plugin_chat_contextmessage`，`(session_id, context_index, index)`
  复合主键。`context_index` 只增不减，最大的就是最新会话；`index` 在同一
  `context_index` 内递增。`role` 为 system/user/assistant/tool，user 消息再按
  `sub_type` 分为 event/message/meta；`display_only` 标记只用于展示、不进入 LLM
  消息列表的消息（被拦截的用户消息、实际发送出去的回复）。
- **block**：事件总结的单位，默认 50 条消息一个 block（`block_id` 同时写进
  `SessionEvent`）。block 一旦提交给事件总结就立即冻结并启用新的 `block_id`，
  因此提前触发（例如第 30 条）得到的是独立 block。`block_id = 0` 是 system/meta
  前导消息，不参与事件总结与滑动窗口。
- **恢复与重置**：启动时恢复最大的 `context_index`；若最后一条消息早于当天 2:00
  则立即 reset。reset 会保存现有记录后换用新的 `context_index`，重新注入 system
  prompt 与会话元数据（meta）。内存中的消息每 5 分钟（以及每次定时任务）写回数据库。
- **锁定与 cursor**：`MessageQueue` 请求 LLM 时通过 `acquire_cursor()` 锁定 context
  并分配 `request_id`。`request_id` 只打在 message queue 推送上来的消息（LLM 输出与
  工具返回）上，请求结束由 cursor 汇报成功/失败，失败时只删除这些消息——user/system
  消息（含注入进请求的图片与提示）不会因为一次请求失败而丢失。锁定最长 10 分钟，
  缓冲队列出现 `trigger_type=all` 的消息时刷新限时，超时以失败解锁。cursor 失效后
  继续操作会抛 `MessageCursorClosed`。
- **双缓冲队列**：processor 推送的消息在锁定期间进入 processor 缓冲队列；一旦其中
  出现 `trigger_type=all` 的消息或事件，整队移交给 message queue 的缓冲队列，
  message queue 每轮请求先提交完整消息列表、再拉取该队列的增量消息（拉取即写入
  context）。请求结束后 processor 缓冲队列的剩余消息全部加入 context。
- **滑动窗口**：距离上一次请求（最后一条带 `request_id` 的消息）超过 10 分钟时，
  从新到旧遍历 block，用 Jev 判断某个 block 的事件是否仍出现在最新 block 的事件中，
  不再相关则删除该 block 及其之前的全部消息并更新 meta；最新 block 永不删除。
- **归档**：每天 7:00 把最后一条消息超过三天的 context 从数据库搬到 LocalStore 的
  json（`core/context_archive.py`）。

### Token Bucket 流控

基于令牌桶算法控制回复频率，替代旧版的欲望（desire）机制。

```python
self.token_bucket = TokenBucket(10, -2)
```

- 每条消息按长度加权积累 token（短消息 0.8，长消息 1.0）
- 提及机器人额外加 1.0 token
- 回复时按字数消耗 token（每 18 字消耗 1 token）
- token 为负时禁止回复，定时恢复

### 消息截断检测

在非 @ 场景下，使用 AI 判断最近消息是否构成完整话题：

```python
is_truncated = await self.check_message_truncated()
```

如果 AI 返回 `true`，说明话题已自然结束，跳过回复，避免在话题切换后仍延续旧话题。

### 系统提示生成

每次生成回复前动态构建系统提示，注入以下上下文：

- 群聊名称和身份设定（`identity` prompt）
- 当前时间和情绪状态（`StatusManager`）
- 发送者信息：昵称、好感度、好感度等级、用户画像
- 关键词触发的笔记（`NoteManager`）
- 即时记忆（`InstantMemory`，带分类和过期等级）
- 最近活动记录（意识系统的行动历史）
- Token Bucket 余额

### 工具系统

通过 `ToolManager` 管理工具选择和调用：

| 工具 | 功能 |
|------|------|
| `browse_webpage` | 网页浏览 |
| `web_search` | 搜索引擎 |
| `request_wolfram_alpha` | 数学/科学计算 |
| `search_abbreviation` | 缩写查询 |
| `describe_bilibili_video` | B站视频解析（可选 `query` 参数用于查询视频中的具体内容） |
| `resolve_b23_url` | B站短链解析 |
| `vm_*` | 虚拟机操作（沙箱执行） |
| `StickerTools` | 表情包推荐和发送 |

工具按场景选择：`group` 模式用于群聊回复，`agent` 模式用于 AI Agent 自主推理。

### AI Agent

`AskAISession` 封装了独立的 AI 推理会话，用于需要自主工具调用的复杂任务：

```python
ai_agent = AskAISession(lang_str, tool_manager)
receipt = await ai_agent.ask_ai(query)  # 立即返回受理提示，研究在后台进行
```

与普通回复不同，AI Agent 可以自主决定调用哪些工具并迭代推理。

`ask_ai` 是完全异步的工具：调用后立即返回一条「已转入后台」的受理提示，研究任务在后台继续执行；
处理完成后（失败时同样）通过触发类型为 `all` 的事件向会话汇报结果。
同一个 `query` 在完成前重复调用会复用已有任务，不会重复消耗 API。

### 意识系统（Ego）

`MainSession` 作为机器人的"意识"，管理自主行为：

- **状态机**：`ACTIVE`（活跃）/ `SLEEPING`（睡眠）
- **无聊度检测**：遍历群聊，当多个群不活跃时触发自主行为
- **自主行动**：发私聊消息、写博客、休息等
- **睡眠控制**：每天 8:30 AI 决定当日睡眠时间，通过 `SleepController` 管理
- **定时思考**：每 5 分钟触发一次思考循环，决定是否采取行动

### 即时记忆

从最近消息中由 AI 提取的短期记忆，带分类和过期机制：

```python
await post_instant_memory(
    category="topic",
    content="用户在讨论 Python 异步编程",
    keywords=["Python", "异步"],
    expire_level=3,
)
```

- 按关键词匹配注入上下文
- 支持跨群关联
- 有过期等级控制生命周期

### 主动私聊

每小时遍历私聊会话（8:00-23:00），根据用户好感度和在线状态主动发起对话。

### 情绪系统

`StatusManager` 管理机器人的情绪状态，影响回复风格：

- 情绪状态（`MoodEnum`）影响系统提示中的语气描述
- 情绪保持度（`mood_retention`）控制情绪变化频率
- 情绪原因动态更新

## 回复决策流程

```
消息进入
  │
  ├─ 被 @ → 直接触发回复
  │
  ├─ 普通消息 → Token Bucket 检查
  │     │
  │     ├─ token ≤ 0 → 跳过
  │     │
  │     ├─ 冷却期内 → 跳过
  │     │
  │     ├─ 消息截断检测 → 话题已结束 → 跳过
  │     │
  │     └─ 概率采样 → 触发回复
  │
  └─ 事件（戳一戳/表情回应/撤回等）→ 概率触发
```

## 用户行为评判

机器人可以对用户行为进行评分（-2 到 +2），影响好感度：

```python
await judge_user_behavior(nickname, score=1, reason="有趣的发言")
```

- 正分增加好感度，负分降低
- 有冷却时间（正分 1 小时，负分 0.5 小时）和每日上限
- 评分后通过 reaction 反馈到具体消息

## 文件结构

```
nonebot_plugin_chat/
├── core/
│   ├── processor.py      # MessageProcessor 核心处理
│   ├── context.py        # ChatContext 上下文管理（消息表 / block / 锁 / 滑动窗口）
│   ├── context_archive.py # 过期 context 的每日归档
│   ├── message.py        # MessageQueue 消息队列管理
│   ├── matchers.py       # 消息匹配器
│   ├── proactive_chat.py # 主动私聊
│   ├── ego/              # 意识系统
│   │   ├── main_session.py   # MainSession 主会话
│   │   └── sleep_controller.py # 睡眠控制
│   └── session/          # 会话管理
│       ├── base.py       # BaseSession 基类
│       ├── group.py      # GroupSession 群聊
│       └── private.py    # PrivateSession 私聊
├── utils/
│   ├── ai_agent.py       # AI Agent 推理会话
│   ├── tool_manager.py   # 工具管理
│   ├── tools/            # 工具实现
│   ├── note_manager.py   # 笔记系统
│   ├── instant_mem.py    # 即时记忆
│   ├── status_manager.py # 情绪状态管理
│   ├── sticker_manager.py # 贴纸管理
│   ├── token_bucket.py   # Token Bucket 流控
│   ├── prompt.py         # Prompt 模板管理
│   ├── message.py        # 消息解析工具
│   └── trigger.py        # 触发器
├── models.py             # 数据模型
├── enums.py              # 枚举定义
└── types.py              # 类型定义
```
