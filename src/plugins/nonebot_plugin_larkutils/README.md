# nonebot-plugin-larkutils

Moonlark 工具插件

## 使用

```python
from nonebot import require

reqiure("nonebot_plugin_larkutils")

from ..nonebot_plugin_larkutils import *

lang = LangHelper()
```

### 获取 UserID (依赖注入)

> 以下为定义代码而不是调用方法

```python
def _get_user_id(event: Event) -> str
get_user_id = Depends(_get_user_id)
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