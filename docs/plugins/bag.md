# Bag

`nonebot_plugin_bag` 提供了一些方法来操作用户的背包。

## 获取背包内的指定物品 `get_bag_item`

```python
async def get_bag_item(user_id: str, index: int, ignore_lock: bool = False) -> BagItem:
```

获取背包中指定索引的物品。

### 参数

- `user_id`: 用户ID
- `index`: 物品索引编号
- `ignore_lock`: 是否忽略物品锁定，默认为 `False`

### 返回

`BagItem` - 物品对象

### 异常

- `IndexError`: 找不到物品

## 获取背包内物品列表 `get_bag_items`

```python
async def get_bag_items(user_id: str, ignore_lock: bool = False, ignore_locked_item: bool = True) -> list[BagItem]:
```

获取用户背包中的所有物品列表。

### 参数

- `user_id`: 用户ID
- `ignore_lock`: 是否忽略物品锁定，默认为 `False`
- `ignore_locked_item`: 忽略已锁定的物品（与 `ignore_lock` 同时设置时忽略此设置），默认为 `True`

### 返回

`list[BagItem]` - 物品列表

## 获取背包内物品数量 `get_items_count`

```python
async def get_items_count(user_id: str) -> int:
```

获取用户背包中的物品数量。

### 参数

- `user_id`: 用户ID

### 返回

`int` - 物品数量

## 给予用户物品 `give_item_by_list`

```python
async def give_item_by_list(user_id: str, items: list[DictItemData]) -> None:
```

通过物品数据列表给予用户物品。

### 参数

- `user_id`: 用户ID
- `items`: 物品数据列表

### 返回

`None`

## 给予用户物品 `give_item_by_data`

```python
async def give_item_by_data(user_id: str, items: GivenItemsData) -> None:
```

通过物品数据给予用户物品、经验、VimCoin等。

### 参数

- `user_id`: 用户ID
- `items`: 物品数据，包含物品列表、经验、VimCoin等

### 返回

`None`