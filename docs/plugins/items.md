# Items

`nonebot_plugin_items` 提供了 Moonlark 中的物品基类，和物品注册支持。

不建议在这个插件以外的位置注册物品。

## 物品基类 `Item`

```python
class Item(ABC):
```

物品基类，所有物品都应继承此类。

### 属性

- `properties`: 物品特性
- `lang`: 本地化助手

### 方法

- `__init__(self, properties: ItemProperties = get_properties())`: 初始化物品
- `getProperties(self) -> ItemProperties`: 获取物品特性
- `setupLang(self) -> None`: 抽象方法，设置本地化助手
- `getLocation(self)`: 获取物品位置
- `getName(self, stack: "ItemStack") -> str`: 获取物品名称
- `getDefaultName(self, stack: "ItemStack") -> str`: 获取物品默认名称
- `getText(self, key: str, user_id: str, *args, **kwargs) -> str`: 获取本地化文本
- `isUseable(self, stack: "ItemStack") -> bool`: 检查物品是否可使用
- `getDefaultDescription(self, user_id: str) -> str`: 获取物品默认描述
- `getDescription(self, stack: "ItemStack") -> str`: 获取物品描述

## 带使用操作的物品的基类 `UseableItem`

```python
class UseableItem(Item, ABC):
```

可使用物品的基类，继承自 `Item`。

### 方法

- `__init__(self, properties: ItemProperties = get_properties()) -> None`: 初始化可使用物品
- `useItem(self, stack: "ItemStack", *args, **kwargs) -> Any`: 抽象方法，使用物品

## 物品特性 `ItemProperties`

```python
class ItemProperties(TypedDict):
    useable: bool
    star: Literal[1, 2, 3, 4, 5]
    max_stack: int
    multi_use: bool
```

物品特性类型定义。

### 字段

- `useable`: 是否可使用
- `star`: 物品星级（1-5）
- `max_stack`: 最大堆叠数
- `multi_use`: 是否可多次使用

## 创建物品特性 `get_properties`

```python
def get_properties(
    useable: bool = False,
    star: Literal[1, 2, 3, 4, 5] = 2,
    max_stack: int = 64,
    multi_use: bool = False,
) -> ItemProperties:
```

创建物品特性对象。

### 参数

- `useable`: 是否可使用，默认为 `False`
- `star`: 物品星级（1-5），默认为 `2`
- `max_stack`: 最大堆叠数，默认为 `64`
- `multi_use`: 是否可多次使用，默认为 `False`

### 返回

`ItemProperties` - 物品特性对象

## 物品注册池 `registry`

```python
class Registry(typing.Generic[T1]):
```

物品注册池，用于注册和管理物品。

### 方法

- `registry(self, location: ResourceLocation, value: T1) -> tuple[ResourceLocation, T1]`: 注册物品
- `getValue(self, location: ResourceLocation) -> T1`: 根据位置获取物品
- `getKey(self, value: T1) -> ResourceLocation`: 根据物品获取位置
- `getEntries(self) -> list[tuple[ResourceLocation, T1]]`: 获取所有注册项
