# nonebot-plugin-larklang

Moonlark 本地化插件

## 使用

```python
from nonebot import require

reqiure("nonebot_plugin_larklang")

from ..nonebot_plugin_larklang import LangHelper

lang = LangHelper()
```

> LangHelper 的 name 参数为空时 plugin_name 将为模块名（不包含 `nonebot_plugin_`）
>
> 对应语言文件位于 `src/lang/<语言，默认为 zh_hans>/<plugin_name>.yaml`

### 获取文本

```python
async def text(self, key: str, user_id: str | int, *args, **kwargs) -> str
```

### 发送文本

```python
async def send(
    self,
    key: str,
    user_id: str | int,
    *args,
    matcher: Matcher = Matcher(),
    at_sender: bool = True,
    reply_message: bool = False,
    **kwargs
) -> None
```

### 回复消息

```python
async def reply(
    self,
    key: str,
    user_id: str | int,
    *args,
    **kwargs
) -> None
```

### 回复并结束处理

```python
async def finish(
    self,
    key: str,
    user_id: str | int,
    *args,
    matcher: Matcher = Matcher(),
    at_sender: bool = True,
    reply_message: bool = False,
    **kwargs
) -> None
```

## 创建本地化语言

在 `src/lang` 下创建一个文件夹作为语言文件夹

创建一个 `language.toml`，填入以下内容

```toml
[language]
# 版本
version = 
# 创作者
author = 

[display]
# 简介（可选）
description = 
```

> 请自行填写具体内容

之后仿照 `zh_hans` 编写 `yaml` 内容

## 许可证

```
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
```