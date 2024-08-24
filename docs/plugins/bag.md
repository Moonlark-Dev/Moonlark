# Bag

## 物品类型

```python
class BagItem
```

> Import 位置： `src.plugins.nonebot_plugin_bag.item.BagItem`

### 属性 

- `index` (`int`): 在用户背包中的位置
- `stack` ([`ItemStack`][2]): 物品

[2]: https://github.com/Moonlark-Dev/Moonlark/blob/main/src/plugins/nonebot_plugin_item/base/stack.py#L13

### 方法

一般的使用中不需要用到此类提供的方法，可前往 [源代码][3] 阅读。

[3]: https://github.com/Moonlark-Dev/Moonlark/blob/main/src/plugins/nonebot_plugin_bag/item/__init__.py#L16

## 物品锁

为了防止 Bug 造成的意外，我们给背包中的每组物品添加了物品锁定。在背包物品操作类（`BagItem`）中，没有锁定的物品的更改将不会写入数据库。

物品数据的更改会在 `BagItem` 对象销毁时保存，已上锁的物品会在 `BagItem` 对象被销毁或启动时自动解锁。

## 获取物品

```python
async def get_bag_item(user_id: str, index: int, ignore_lock: bool = False) -> BagItem
```

> Import 位置： `src.plugins.nonebot_plugin_bag.utils.item.get_bag_item`

### 参数

- `user_id`: 用户
- `index`: 物品索引位置
- `ignore_lock`: 是否忽略物品锁定（忽略后不会上锁物品）

### 返回

`BagItem` - 物品对象

### 异常

- `IndexError` - 找不到物品
- `ItemLockedError` - 物品已锁定

## 获取物品列表

```python
async def get_bag_items(user_id: str, ignore_lock: bool = False, ignore_locked_item: bool = True) -> list[BagItem]
```

> Import 位置： `src.plugins.nonebot_plugin_bag.utils.item.get_bag_items`

### 参数

- `user_id`: 用户
- `ignore_lock`: 是否忽略物品锁定（忽略后不会上锁物品）
- `ignore_locked_item`: 忽略上锁的物品（忽略后将在因物品被锁定而上锁失败时主动忽略物品）

### 返回

`list[BagItem]` - 物品列表

### 异常

- `IndexError` - 找不到物品
- `ItemLockedError` - 物品已锁定

## 给予物品

> Import 位置： `src.plugins.nonebot_plugin_bag.utils.give`

::: tip

以下列出的两种方法等效但是接受的物品列表类型不一致。

:::

```python
async def give_item_by_list(user_id: str, items: list[DictItemData]) -> None
```

```python
async def give_item_by_data(user_id: str, items: GivenItemsData) -> None:
```

### 参数类型

- `list[DictItemData]`: [查看定义][1]
- `GivenITemsData`: [查看定义][4]

[1]: https://github.com/Moonlark-Dev/Moonlark/blob/main/src/plugins/nonebot_plugin_item/types.py#L5
[4]: https://github.com/Moonlark-Dev/Moonlark/blob/main/src/plugins/nonebot_plugin_bag/types.py#L15





