# nonebot-plugin-larkhelp

Moonlark 命令帮助

## 使用

```
help [command]
```

## 配置

插件目录下的 `help.yaml` 文件（以 LarkHelp 的帮助为例）：

```yaml
# 插件名（同初始化 LangHelper 的 name 参数，默认为模块名（不包含 nonebot_plugin_））
plugin: larkhelp
# 命令列表
commands:
  # 命令名
  help:
    # 简介 （注意：以下所有值都应该为 larklang 本地化键名）
    description: help.description
    # 详细信息
    details: help.details
    # 用法表
    usages:
      - help.usage_list
      - help.usage_command
```

之后，在插件的本地化文件中填入对应内容

### 用法

用法表中用法的格式如下

```
命令 子命令 [-f|--foo <参数>] <参数> [可选参数]
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