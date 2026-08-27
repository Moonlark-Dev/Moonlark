# Button

`nonebot_plugin_larkutils.button` 是 Moonlark 中用于构建 QQ 官方机器人按钮消息及处理按钮交互的工具模块。

QQ 官方机器人按钮限制：

- 按钮不能单独发送，必须搭配 Markdown 消息段
- 每行按钮建议不超过 5 个
- `button_data` 回调数据最长 32 字节
- 自定义 keyboard 和模版 keyboard 二选一

## 基础用法

```python
keyboard = build_keyboard(
    [build_callback_button("confirm", "确认", "confirm"), build_callback_button("cancel", "取消", "cancel")],
    [build_link_button("docs", "文档", "https://moonlark.dev")],
)
await send_keyboard_to_group(bot, group_openid, "**请选择操作**", keyboard)
```

## 按钮类型 `ButtonType`

```python
ButtonType = Literal["link", "callback", "qqbot", "minigame"]
```

按钮动作类型：

- `link`: 打开链接
- `callback`: 回调机器人
- `qqbot`: 打开指定 qqbot
- `minigame`: 跳转小程序

## 按钮定义 `ButtonDef`

```python
class ButtonDef:
    def __init__(
        self,
        id: str,
        label: str,
        action_type: ButtonType = "callback",
        data: str | None = None,
        style: int = 1,
        visited_label: str | None = None,
        url: str | None = None,
        permission_type: int = 0,
        permission_user_ids: list[str] = ...,
        permission_role_ids: list[str] = ...,
        reply: bool = False,
        enter: bool = False,
        unsupport_tips: str | None = None,
    ) -> None:
```

单个按钮定义数据类。

### 字段

- `id`: 按钮唯一标识，也是交互事件中返回的 `button_id`
- `label`: 按钮显示文字
- `action_type`: 动作类型，见 `ButtonType`
- `data`: 回调数据（`action_type=callback` 时最长 32 字节）
- `style`: 按钮样式（1=蓝色主按钮, 2=灰色）
- `visited_label`: 点击后显示的文字
- `url`: 链接地址（`action_type=link` 时使用）
- `permission_type`: 权限类型（0=所有人可点, 1=指定用户/身份组）
- `permission_user_ids`: 允许点击的用户 openid 列表（`permission_type=1`）
- `permission_role_ids`: 允许点击的身份组 ID 列表（`permission_type=1`）
- `reply`: 是否弹出回复框
- `enter`: 是否自动发送（需 `reply=True`）
- `unsupport_tips`: 不支持时的提示文字

## 键盘定义 `KeyboardDef`

```python
class KeyboardDef:
    def add_row(self, *buttons: ButtonDef) -> KeyboardDef:
    def add_button(self, row_index: int, button: ButtonDef) -> KeyboardDef:
```

按钮键盘定义，支持链式构建。

### 方法说明

- `add_row`: 添加一行按钮
- `add_button`: 在指定行添加按钮，行不存在则自动创建

## 构建单个按钮 `build_button`

```python
def build_button(
    id: str,
    label: str,
    *,
    action_type: ButtonType = "callback",
    data: str | None = None,
    style: int = 1,
    visited_label: str | None = None,
    url: str | None = None,
    permission_type: int = 0,
    permission_user_ids: list[str] | None = None,
    permission_role_ids: list[str] | None = None,
    reply: bool = False,
    enter: bool = False,
    unsupport_tips: str | None = None,
) -> ButtonDef:
```

构建单个按钮定义。

### 参数

- `id`: 按钮唯一标识
- `label`: 按钮显示文字
- `action_type`: 动作类型（link/callback/qqbot/minigame）
- `data`: 回调数据，最长 32 字节
- `style`: 按钮样式（1=蓝色, 2=灰色）
- `visited_label`: 点击后显示的文字
- `url`: 链接地址（`action_type=link`）
- `permission_type`: 权限类型（0=所有人, 1=指定）
- `permission_user_ids`: 允许点击的用户 openid 列表
- `permission_role_ids`: 允许点击的身份组 ID 列表
- `reply`: 是否弹出回复框
- `enter`: 是否自动发送
- `unsupport_tips`: 不支持时的提示

### 返回

`ButtonDef` - 按钮定义对象

## 构建链接按钮 `build_link_button`

```python
def build_link_button(
    id: str,
    label: str,
    url: str,
    *,
    style: int = 1,
    visited_label: str | None = None,
) -> ButtonDef:
```

构建链接按钮的快捷函数（`action_type="link"`）。

### 参数

- `id`: 按钮唯一标识
- `label`: 按钮显示文字
- `url`: 点击后打开的链接地址
- `style`: 按钮样式
- `visited_label`: 点击后显示的文字

### 返回

`ButtonDef` - 按钮定义对象

## 构建回调按钮 `build_callback_button`

```python
def build_callback_button(
    id: str,
    label: str,
    data: str,
    *,
    style: int = 1,
    visited_label: str | None = None,
    reply: bool = False,
    enter: bool = False,
) -> ButtonDef:
```

构建回调按钮的快捷函数（`action_type="callback"`）。

### 参数

- `id`: 按钮唯一标识
- `label`: 按钮显示文字
- `data`: 回调数据（最长 32 字节）
- `style`: 按钮样式
- `visited_label`: 点击后显示的文字
- `reply`: 是否弹出回复框
- `enter`: 是否自动发送

### 返回

`ButtonDef` - 按钮定义对象

## 构建键盘 `build_keyboard`

```python
def build_keyboard(*rows: list[ButtonDef]) -> KeyboardDef:
```

按行构建键盘定义。

```python
keyboard = build_keyboard(
    [btn_confirm, btn_cancel],
    [btn_help],
)
```

### 参数

- `rows`: 每行按钮列表

### 返回

`KeyboardDef` - 键盘定义对象

## 构建带按钮的消息 `build_keyboard_message`

```python
def build_keyboard_message(
    markdown_content: str,
    keyboard: KeyboardDef,
    *,
    template_id: str | None = None,
    custom_template_id: str | None = None,
) -> Message:
```

构建带按钮的 QQ 消息。按钮消息必须搭配 Markdown 才能发送（msg_type=2）。

### 参数

- `markdown_content`: Markdown 正文内容
- `keyboard`: 键盘定义
- `template_id`: Markdown 模版 ID（与 `custom_template_id` 二选一）
- `custom_template_id`: 自定义模版 ID

### 返回

`Message` - QQ Adapter 消息对象

## 使用模版构建带按钮的消息 `build_keyboard_message_by_template`

```python
def build_keyboard_message_by_template(
    template_id: str,
    params: dict[str, list[str]],
    keyboard: KeyboardDef,
) -> Message:
```

使用 Markdown 模版构建带按钮的消息。

### 参数

- `template_id`: Markdown 模版 ID
- `params`: 模版参数 `{key: [values]}`
- `keyboard`: 键盘定义

### 返回

`Message` - QQ Adapter 消息对象

## 响应按钮交互 `respond_interaction`

```python
InteractionCode = Literal[0, 1, 2, 3, 4, 5]

async def respond_interaction(
    bot: QQBot,
    event: InteractionCreateEvent,
    code: InteractionCode = 0,
) -> None:
```

响应按钮交互事件。

### 参数

- `bot`: QQ Bot 实例
- `event`: 交互事件
- `code`: 响应码（0=弹 Toast, 1=弹输入框, 2=更新按钮状态, 3=跳转链接, 4=loading, 5=跳转小程序）

### 返回

`None`

## 提取按钮交互数据 `get_interaction_data`

```python
def get_interaction_data(event: InteractionCreateEvent) -> dict[str, str | None]:
```

从交互事件中提取按钮数据，用于在回调中识别按钮及点击者。

```python
data = get_interaction_data(event)
# {"button_id": ..., "button_data": ..., "user_id": ..., "message_id": ...}
```

### 参数

- `event`: 交互事件

### 返回

`dict[str, str | None]` - 包含以下字段的字典：

- `button_id`: 按钮 ID
- `button_data`: 回调数据
- `user_id`: 点击用户 ID
- `message_id`: 原消息 ID

## 发送带按钮的消息到群聊 `send_keyboard_to_group`

```python
async def send_keyboard_to_group(
    bot: QQBot,
    group_openid: str,
    markdown_content: str,
    keyboard: KeyboardDef,
    *,
    template_id: str | None = None,
    custom_template_id: str | None = None,
) -> None:
```

构建并发送带按钮的消息到群聊。

### 参数

- `bot`: QQ Bot 实例
- `group_openid`: 群聊 openid
- `markdown_content`: Markdown 正文
- `keyboard`: 键盘定义
- `template_id`: Markdown 模版 ID
- `custom_template_id`: 自定义模版 ID

### 返回

`None`

## 发送带按钮的消息到私聊 `send_keyboard_to_c2c`

```python
async def send_keyboard_to_c2c(
    bot: QQBot,
    openid: str,
    markdown_content: str,
    keyboard: KeyboardDef,
    *,
    template_id: str | None = None,
    custom_template_id: str | None = None,
) -> None:
```

构建并发送带按钮的消息到私聊。

### 参数

- `bot`: QQ Bot 实例
- `openid`: 用户 openid
- `markdown_content`: Markdown 正文
- `keyboard`: 键盘定义
- `template_id`: Markdown 模版 ID
- `custom_template_id`: 自定义模版 ID

### 返回

`None`