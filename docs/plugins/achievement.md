# Achievement

`nonebot_plugin_achievement` 是 Moonlark 中成就功能的实现


::: tip 成就ID

每个成就都有一个唯一的 ID，是一个 [`ResourceLocation`](https://github.com/Moonlark-Dev/Moonlark/blob/main/src/plugins/nonebot_plugin_item/registry/registry.py#L8) 对象。

:::

## 成就注册

成就文件为 [`src/plugins/nonebot_plugin_achievement/achievements/<namespace>.json`](https://github.com/Moonlark-Dev/Moonlark/tree/main/src/plugins/nonebot_plugin_achievement/achievements)，其中 `<namespace>` 为成就的命名空间，一般与成就所在的插件名一致。

### 结构

- `lang`: 插件本地化信息
  - `plugin`: 本地化插件名
  - `key`: 成就本地化基键（即二级键名）
- `achievements`: 成就表

#### 成就表

成就表使用 `key-value` 对应，键为成就的 `path`，值为成就的信息，结构如下：

- `required_unlock_count`: 需要解锁次数（请求解锁指定次数后成就才算达成）
- `awards`: 奖励表（为 [`list[DictItemData]`](https://github.com/Moonlark-Dev/Moonlark/blob/main/src/plugins/nonebot_plugin_item/types.py#L5)）

### 本地化

成就的名称需要本地化，同命名空间所有成就的标题都在同一个二级键下。与 `lang` 的配置对应为：`<plugin>.<key>.<成就path>`

## 请求解锁

```python
async def unlock_achievement(id_: ResourceLocation, user_id: str, count: int = 1) -> None:
```

请求解锁指定成就。

### 参数

- `id_`: 成就的ID
- `user_id`: 解锁成就的用户
- `count`: 请求解锁的次数

### 返回

`None`

### 解锁次数

对于部分需要多次挑战累加才能解锁的成就可以使用"解锁次数"，在调用 `unlock_achievement` 时会累加 `count` 参数，如果总数大于等于 `required_unlock_count` 的值，成就就会真正被解锁。
