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
| `describe_bilibili_video` | B站视频解析 |
| `resolve_b23_url` | B站短链解析 |
| `vm_*` | 虚拟机操作（沙箱执行） |
| `StickerTools` | 表情包推荐和发送 |

工具按场景选择：`group` 模式用于群聊回复，`agent` 模式用于 AI Agent 自主推理。

### AI Agent

`AskAISession` 封装了独立的 AI 推理会话，用于需要自主工具调用的复杂任务：

```python
ai_agent = AskAISession(lang_str, tool_manager)
result = await ai_agent.ask_ai(query)
```

与普通回复不同，AI Agent 可以自主决定调用哪些工具并迭代推理。

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
