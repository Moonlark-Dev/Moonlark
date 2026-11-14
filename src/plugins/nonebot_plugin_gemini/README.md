# nonebot_plugin_gemini

Gemini SDK 封装，接口与 `nonebot_plugin_openai` 对齐：调用方在 `fetch_message` /
`fetch_json` / `MessageFetcher` 之间切换即可换用 Gemini，消息仍然是 OpenAI 风格的 dict
（`utils/convert.py` 在发请求前转换成 Gemini 的 `Content`）。

## 功能

- **工具调用循环**：每轮请求自动执行模型要求调用的工具，把结果作为
  `function_response` 送回模型，直到模型不再要求调用工具（`utils/chat.py`）；
- **工具列表生成**：从 `src/prompt/__tools__/<函数名>.yaml` 生成
  `FunctionDeclaration`，参数以 JSON Schema 形式传给 SDK（`utils/functions.py`）；
- **AxonHub 链路标识**：请求头写入 Thread Id（`<identify_prefix> - <identify>`）、
  可配置的多个 Trace Id（同一个 `trace_id`）与溯源 `HTTP-Referer`，并可用
  `set_custom_trace_id` 覆盖（Chat 用 `session:context_index`）；
- **图片拦截恢复**：`finish_reason` / `promptFeedback` 表明整轮被安全策略拦截时，调用
  调用方提供的 `on_image_blocked` 回调（把图片替换成文字描述）后重试，默认最多 2 次；
- **Gemini 3 thought_signature**：函数调用的 `thought_signature` 会随 OpenAI 风格
  `tool_calls` 的额外字段保存，回放历史时再还原；发给 OpenAI 前由
  `nonebot_plugin_openai.utils.sanitize.strip_tool_call_extras` 剔除。

## 配置

| 变量 | 说明 |
| --- | --- |
| `GEMINI_API_KEY` | Gemini API Key；不配置时插件仍可加载，真正请求时才报错 |
| `GEMINI_BASE_URL` | API 地址，使用 AxonHub 等网关时填写，留空使用官方地址 |
| `GEMINI_API_VERSION` | API 版本，留空由 SDK 决定（v1）；网关只提供 v1beta 时填 `v1beta` |
| `GEMINI_DEFAULT_MODEL` | 默认模型（未通过 `/gem-model` 覆盖时使用） |

可选项见 `config.py`：`GEMINI_THREAD_HEADER`（默认 `AH-Thread-Id`）、
`GEMINI_TRACE_HEADERS`（默认 `["AH-Trace-Id"]`）、`GEMINI_IMAGE_BLOCK_RETRIES`、
`GEMINI_THINKING_LEVELS` / `GEMINI_THINKING_BUDGETS`。

`reasoning_effort` 默认不会传递给 Gemini（不同模型对 `thinking_level` /
`thinking_budget` 的支持不一致，传错会直接失败），需要时用上面两个映射表显式配置：
Gemini 3 及以后用 `GEMINI_THINKING_LEVELS`（如 `{"low": "LOW", "medium": "HIGH"}`），
更早的模型用 `GEMINI_THINKING_BUDGETS`（如 `{"medium": 8192}`）。

## 命令

- `/gem-model`：查看 Gemini 模型配置与可用模型列表；
- `/gem-model <模型名>`：更换默认模型；
- `/gem-model <模型名> <应用标识>`：设置应用专用模型（如 `Chat`）；
- `/gem-model :default: <应用标识>`：删除应用配置。

仅超级用户可用，配置保存在 `nonebot_plugin_gemini_geminimodelconfig`。

## 使用

```python
from nonebot_plugin_gemini import fetch_message, fetch_json
from nonebot_plugin_gemini.utils.chat import MessageFetcher
from nonebot_plugin_gemini.utils.message import generate_message, get_message_text
```

与 OpenAI 插件相同，`identify` 用于选择应用专用模型，也用于请求头里的 Thread Id。
