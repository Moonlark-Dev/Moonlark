# 快速开始

## 谁适合阅读本文档？

在阅读本文档前，请确保您符合以下条件：

1. 掌握基本的 [Python3][1] 语法，能够使用其进行开发。
2. 了解 [NoneBot2][2] 框架的使用及其插件结构。
3. 能够访问和使用 [GitHub][3]，了解 Git 的基本使用方法。
4. 能够使用 [nb-cli][4] 和 [poetry][5]。

## 代码规范

在仓库的 [CONTRIBUTING.md][5] 中，我们已地列出了需要遵守的代码规范，对于其中提到的由 Moonlark 实现的插件，我们在 [插件表][6] 中编写了文档。

::: tip

部分带有自动导入功能的编辑器、IDE 及语言服务器（如 VSCode）可能将相对导入的根目录识别为 `src/` 但实际上为仓库根目录。

### 正确

```python
from src.plugins.nonebot_plugin_larkutils import get_user_id
```

#### 使用相对路径导入

```python
from ..nonebot_plugin_larkutils import get_user_id
```

### 错误

```python
from plugins.nonebot_plugin_larkutils import get_user_id
```

:::

::: tip

有一部分编辑器或 IDE （如 PyCharm）可能在重构时在 `src/` 和 `src/plugins/` 下建立空的 `__init__.py` 文件，请删除它或添加为 Ignore。

:::


## 开始

[初始化开发环境][7]



[1]: https://python.org
[2]: https://nonebot.dev
[3]: https://github.com
[4]: https://cli.nonebot.dev/
[5]: https://python-poetry.org/
[6]: /plugins/index
[7]: create-develop-environment
