# nonebot-plugin-larklang

Moonlark 本地化插件

## 使用

```python
from nonebot import require

reqiure("nonebot_plugin_larklang")

from ..nonebot_plugin_larklang import LangHelper

lang = LangHelper()
```

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