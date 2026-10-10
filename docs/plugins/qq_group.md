# QQ Group

`nonebot_plugin_qq_group` 维护 QQ 官方 Bot 的群聊信息与群成员列表缓存，供
`everyday_wife`、`chat`、`message_summary` 等插件引用。

QQ 开放平台的[获取群基本信息](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_info.get.html)
与[获取群成员列表](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_members.get.html)
接口都只对白名单机器人开放，群成员列表还有分页（每页 30 条）与频率限制（60 QPM）。
因此插件把接口结果缓存在数据库中，收到 QQ 群消息时登记该群并在后台同步一次，
之后由周期任务按缓存有效期刷新，其余功能只读缓存。

缓存同时会用群成员列表里的昵称补全没有昵称的用户：已注册用户（`UserData`）昵称为空时
填入并标记来源为 `group_member`，未注册用户直接写入 `GuestUser`（来自
`nonebot_plugin_larkuser`，本插件 `require` 了它）。

腾讯接口不可用（适配器抛出 `ActionFailed`，或返回 11253 / 429 等错误）时，读取群成员
列表会临时降级到 `nonebot_plugin_message_summary` 保存的群消息：统计最近约两天在群里
发过言的用户作为活跃成员列表返回，不写回权威缓存。这样即使群成员列表接口暂时不可用，
`everyday_wife` 等依赖群成员列表的功能仍能继续工作。

相关配置见 `.env.template` 中的 `QQ_GROUP_*` 配置项。

## 引用方式

```python
from nonebot_plugin_qq_group import get_group_member_ids

members = await get_group_member_ids(bot, group_openid)
```

插件导出 `QQGroupInfo` / `QQGroupMemberInfo` 两个数据类型，以及下列函数：

```python
async def get_group_name(bot: QQBot, group_openid: str) -> Optional[str]:
```

获取群名称，缓存缺失或过期时调用接口刷新，接口不可用时返回 `None`。

```python
async def get_group_member(group_openid: str, member_openid: str) -> Optional[QQGroupMemberInfo]:
```

按成员 openid 读取缓存的群成员信息（昵称、群角色、入群时间等），未缓存时返回 `None`。

```python
async def get_cached_group_members(group_openid: str) -> list[QQGroupMemberInfo]:
```

读取缓存的群成员列表（不调用接口）。

```python
async def get_group_member_nickname_map(group_openid: str) -> dict[str, str]:
```

构造「昵称 -> 成员 openid」映射，昵称优先取 Moonlark 中的昵称，没有时退回到 QQ 昵称。
Chat 会话解析 @ 时使用该映射。

```python
async def get_group_member_ids(bot: QQBot, group_openid: str) -> list[str]:
```

获取群成员 openid 列表，缓存尚未建立时同步一次。`everyday_wife` 插件用它抽取群成员。

```python
async def ensure_group_members(bot: QQBot, group_openid: str) -> list[QQGroupMemberInfo]:
```

确保群成员缓存可用，从未同步过或缓存为空时同步一次。

```python
async def refresh_group_members(bot: QQBot, group_openid: str) -> list[QQGroupMemberInfo]:
```

忽略缓存有效期，全量重新拉取群成员列表并刷新缓存（含分页、频率限制与昵称补全）。
腾讯接口不可用时返回从 Message Summary 临时还原的活跃成员列表；没有可用消息记录时
退回已有缓存。

```python
async def fetch_group_members_from_message_summary(group_openid: str) -> list[QQGroupMemberInfo]:
```

从 Message Summary 保存的群消息里临时还原活跃成员列表（按最近发言时间倒序），
供群成员列表接口不可用时降级使用；插件未加载、没有记录或查询失败时返回空列表。
成员 ID 优先取消息记录的 `platform_user_id`（即 `event.get_user_id()`，QQ 官方群里
就是 `member_openid`），历史数据没有这一列时退回 Moonlark 主账号 ID。

```python
async def refresh_group_info(bot: QQBot, group_openid: str) -> Optional[QQGroupInfo]:
```

调用接口刷新群基本信息，失败时返回 `None` 并把错误记录到缓存表中。

```python
async def remember_group(group_openid: str, bot_id: str = "") -> None:
```

登记一个 QQ 群（不调用接口），已存在时只补全 `bot_id`。

```python
async def sync_all_groups() -> None:
```

周期任务调用的同步入口，按缓存有效期刷新所有已登记群的群信息与群成员列表。

## 底层接口

`nonebot_plugin_qq_group.client` 直接按 QQ 开放平台文档实现了适配器未提供的两个接口，
导出 `QQGroupAPIError` / `QQGroupPermissionError`（11253 无权限）/ `QQGroupRateLimitError`
（HTTP 429）以及 `fetch_group_info`、`fetch_group_members_page`、`fetch_all_group_members`。

## 数据表

- `nonebot_plugin_qq_group_info`：群基本信息与同步状态；
- `nonebot_plugin_qq_group_member`：群成员列表缓存。

> 这两张表原先由 `nonebot_plugin_larkuser` 维护（表名 `nonebot_plugin_larkuser_qq_group_*`），
> 插件拆分时通过迁移改名，数据保留。
