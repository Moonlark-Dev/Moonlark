# Broadcast HTTP API

`nonebot_plugin_broadcast` 除了 `bcsu` 指令，还提供一组 HTTP 接口，让部署脚本、CI、
管理面板可以直接触发群发并查询进度。

## 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/broadcast` | 受理一次广播，返回 `202` 与广播 id，实际发送在后台进行 |
| `GET` | `/api/broadcast/targets` | 列出群列表及每个群当前是否可广播 |
| `GET` | `/api/broadcast/{broadcast_id}` | 查询广播状态与逐群推送结果 |

## 鉴权

所有接口都要求 `Authorization: Bearer <credential>`，支持两种凭据：

1. **API Token**（机器调用）：在 `.env` 里配置 `BROADCAST_API_TOKENS`，JSON 映射
   「名称 -> token」。名称用于审计（记录里的 `submitter` 是 `api:<名称>`）和限流，
   所以一个调用方对应一个 token，不要多人共用一个。
2. **Moonlark Web 会话**（网页管理端）：沿用 LarkUID 的 `Bearer <sessionID>`，
   会话必须已激活，且用户必须在 `SUPERUSERS` 里；非超管返回 `403`。

```conf
BROADCAST_API_TOKENS='{"ci": "足够长的随机字符串", "ops": "另一个随机字符串"}'
```

设计取舍：

- Token 用 `hmac.compare_digest` 做常数时间比较，避免时序侧信道；
- 不接受 query string / 自定义 header 里的凭据（前者会进入反代访问日志和 Referer）；
- 未配置任何 token 时，机器凭据整体关闭，只接受超管 Web 会话；
- Token 的值不会写进日志，日志里只出现 `api:<名称>`。

## 请求

```http
POST /api/broadcast
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: release-2026-11-29

{
  "content": "## 更新公告\n\n本次更新修复了……",
  "targets": ["123456789", "group_openid_xxx"],
  "buttons": [{"label": "查看", "text": "/bc"}],
  "dry_run": false
}
```

字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `content` | 是 | Markdown 正文，去掉首尾空白后不能为空，默认上限 5000 字符 |
| `targets` | 否 | 只发给这些群；支持 OB11 群号或 QQ `group_openid`。省略表示所有启用群 |
| `buttons` | 否 | QQ 官方按钮；省略表示沿用 `bcsu button` 配置的按钮，传 `[]` 表示这次不带按钮 |
| `dry_run` | 否 | `true` 只校验并返回目标群，不发送，返回 `200` |

`targets` 里的群必须当前可达（存在于 `BroadcastGroup` 且未用 `bc off` 关闭），否则
返回 `400` 并列出不可用的群。

### 为什么要后台发送

一次群发是逐群串行发送的，中间还有 1–7 秒随机间隔，几十个群就要几分钟；如果同步
处理，调用方（以及反向代理的 60 秒超时）会先于广播结束拿到超时错误，重试又可能造成
重复群发。因此接口受理后立即返回 `202`，用 `GET /api/broadcast/{id}` 查询进度。

### 幂等

带 `Idempotency-Key` 时，同一个键重复提交只会产生一次广播：

- 重放返回原广播的当前状态（`202`，`"idempotent": true`），不会再次发送；
- 同一个键配了不同内容（正文/按钮/目标群任一不同）返回 `409`，避免「改了内容但忘记换键」。

幂等键通过 `BroadcastRecord.request_id`（唯一索引）落库，跨进程、重启后依然有效。
一次广播如果最终失败，想重新发送请换一个新的幂等键——同一个键只会返回原来的失败结果。

### 单并发

同一时间只允许一次广播处于 `queued`/`running`。已有广播在发送时再次触发返回 `409`
并带 `Retry-After`，避免两次群发交叠、同一个群收到两条互相矛盾的内容。判断依据是
数据库里的广播记录，所以 `bcsu submit` 正在发送时，HTTP 接口同样会被拒绝。

进程崩溃留下的 `queued`/`running` 记录超过一小时会被视为僵尸并标为 `failed`，
不会永久锁死接口。

### 限流

默认每个调用方（token 名称或超管账号）每分钟最多 5 次，配置项
`BROADCAST_API_RATE_LIMIT` / `BROADCAST_API_RATE_WINDOW`。限流器在进程内计数，
多 worker 部署时实际放行量约为配置值 × worker 数；它用于拦住误触发的循环，不是
对抗恶意流量。

### 响应

```json
{
  "broadcast_id": 12,
  "status": "queued",
  "total": 2,
  "targets": ["123456789", "group_openid_xxx"],
  "idempotent": false
}
```

`GET /api/broadcast/12`：

```json
{
  "broadcast_id": 12,
  "status": "done",
  "total": 2,
  "submitter": "api:ci",
  "request_id": "release-2026-11-29",
  "created_at": "2026-11-29T02:00:00",
  "stats": {"sent": 1, "pending": 1, "failed": 0},
  "events": [
    {"group_key": "123456789", "mode": "active", "status": "sent", "error": null, "...": "..."}
  ]
}
```

`status` 取值：`queued`（已受理，等后台任务开始）、`running`（发送中）、`done`（发送
流程结束，个别群失败看 `events`）、`failed`（流程异常中断）。

`stats.pending` 是 QQ 官方未开启主动消息推送、转入被动补发的群；它们会在该群下一条
消息后延迟三分钟发送，所以 `done` 不代表所有群都已经发出。

## 错误码

| 状态码 | 场景 |
| --- | --- |
| `400` | 正文为空/超长、按钮为空、`targets` 不可用、`Idempotency-Key` 格式错误 |
| `401` | 缺少凭据，或凭据既不是有效 token 也不是有效会话 |
| `403` | Web 会话有效但不是超管 |
| `404` | 广播记录不存在 |
| `409` | 幂等键内容冲突，或已有广播正在进行 |
| `422` | 请求体不是合法 JSON / 缺必填字段（FastAPI 校验） |
| `429` | 触发过于频繁 |

## 示例

```bash
curl -X POST https://moonlark-api.example.com/api/broadcast \
  -H "Authorization: Bearer $BROADCAST_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "## 维护通知\n\n今晚 23:00 重启。", "dry_run": true}'
```
