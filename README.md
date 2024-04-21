# Moonlark

新一代聊天机器人

## 背景

如果你没听过 Moonlark，那你可能听过它的另一个名字——XDbot。

为了解决 XDbot2 代码过于混乱且兼容性极差的问题，我们决定开发一个新项目，它便是 Moonlark。

## 说明

Moonlark 意为「月雀」，是一个多功能的聊天机器人。

Moonlark 是 Moonlark Projects (XDbot Project) 的下一个项目，使用基于 Python3 的 Nonebot2 框架编写。

Moonlark 是开放的、稳定的、非盈利的，我们希望通过这些来吸引更多人参与 Moonlark 项目或使用 Moonlark。

## 使用

Moonlark 目前还在测试中。

## 贡献

您可以通过提交 [议题](https://github.com/Moonlark-Dev/Moonlark/issues/new/choose) 或 [拉取请求](https://github.com/Moonlark-Dev/Moonlark/compare) 参与 Moonlark 项目。

请注意，在参与贡献时，请确保遵守我们的 [贡献者行为守则](CODE_OF_CONDUCT.md)。

### 代码建议

我们建议您在提交代码时遵循一下几个准则，否则您的拉取请求可能会被审核员标记为 `请求更改`：

- 为了确保稳定性和兼容性，我们建议您在提交代码时：
    - 使用 [LocalStore](https://github.com/nonebot/plugin-localstore) 储存文件
    - 使用 [ORM](https://github.com/nonebot/plugin-orm) 储存数据
    - 使用 [UserInfo](https://github.com/noneplugin/nonebot-plugin-userinfo) 或 [LarkUser](src/plugins/nonebot_plugin_larkuser) 获取用户信息
    - 使用 [Session](https://github.com/noneplugin/nonebot-plugin-session) 获取群组信息
    - 使用 [LarkLang](src/plugins/nonebot_plugin_larklang) 作为本地化插件
    - 使用 [HtmlRender](https://github.com/kexue-z/nonebot-plugin-htmlrender) 将 MarkDown、HTML 等渲染为图片
    - 使用 [Alconna](https://github.com/nonebot/plugin-alconna) 解析命令和发送消息
- 在部分耗时操作中（包括但不限于文件读写、网络请求），您需要使用异步以确保它不会阻塞 Moonlark 进程
- 除用户信息（如昵称等）或由用户提交的内容，所有会被用户看到的文本都需要接入本地化
- 所有文件都需要使用 `UTF-8` 编码，您可能要在打开文件时指定编码以确保在 Windows 系统下代码能够正常运行


### 搭建 Moonlark 开发环境

在开发 Moonlark 前，您需要安装 [Poetry](https://python-poetry.org/docs/#installation) 并使用 Poetry 安装依赖：

```bash
poetry install
```
在运行前，您需要将 [`.env.template`](.env.template) 复制为 `.env` 文件并填写相关环境变量。

您可以使用任何工具编写 Moonlark 的代码。当然，我们不建议使用如记事本、写字板之类的非专业工具。

### 更新数据库

在修改数据库模板后，您需要更新 ORM 数据库: 

```bash
nb orm sync
```

由于特殊原因（已知是由 `nonebot-plugin-access-control` 引起的），您可能需要进行以下操作来完成更新:

在数据库（如 `sqlite3 test.db`）执行以下指令:

```sql
drop table accctrl_permission;
drop table accctrl_rate_limit_rule;
drop table accctrl_rate_limit_token;
```

并在 shell 中执行:

```bash
nb orm upgrade
```




## 许可证

Moonlark 基于 `GNU AFFERO GENERAL PUBLIC LICENSE v3.0 (AGPL-3.0)` 开源。

```
    Moonlark - A new ChatBot
    Copyright (C) 2024  Moonlark Development Team

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

## 鸣谢

- [IT Craft Development Team](https://itcdt.top)
- [Nonebot2](https://nonebot.dev)
- 所有开发者、贡献者和用户

