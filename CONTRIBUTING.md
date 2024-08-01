# Moonlark 贡献指南

首先，感谢你愿意为 Moonlark 贡献自己的一份力量！

本指南旨在引导你更规范地向 Moonlark 提交贡献，请务必认真阅读。

## 提交 Issue

在提交 Issue 前，我们建议你先查看 [已有的 Issues](https://github.com/Moonlark-Dev/Moonlark/issues) 以防重复提交。

## Pull Request

### 开发环境搭建

Moonlark 使用 [poetry](https://python-poetry.org/) 管理项目依赖，依赖可以通过以下命令安装：

```bash
poetry install
```

在运行前，您需要将 [`.env.template`](.env.template) 复制为 `.env` 文件并按提示填写相关环境变量。

### 代码规范

我们建议您在提交代码时遵循一下几个准则，否则您的拉取请求可能会被审核员标记为 `请求更改`：

- 为了确保稳定性和兼容性，我们建议您在提交代码时：
    - 使用 [LocalStore](https://github.com/nonebot/plugin-localstore) 储存文件
    - 使用 [ORM](https://github.com/nonebot/plugin-orm) 储存非 BLOB 用户数据
    - 使用 [LarkUser](src/plugins/nonebot_plugin_larkuser) 获取用户信息
    - 使用 [LarkUtils](src/plugins/nonebot_plugin_larkutils) 获取用户 ID 及群组 ID
    - 使用 [LarkLang](src/plugins/nonebot_plugin_larklang) 作为本地化插件
    - 使用 [HtmlRender](https://github.com/kexue-z/nonebot-plugin-htmlrender) 渲染 Markdown
    - 使用 [Render](src/plugins/nonebot_plugin_render) 渲染 Jinja 模板
    - 使用 [Alconna](https://github.com/nonebot/plugin-alconna) 解析命令和发送消息
- 在部分耗时操作中（包括但不限于文件读写、网络请求），您需要使用异步以确保它不会阻塞 Moonlark 进程
- 除用户信息（如昵称等）或由用户提交的内容，所有会被用户看到的文本都需要接入本地化
- 所有文件都需要使用 `UTF-8` 编码，您可能要在打开文件时指定编码以确保在 Windows 系统下代码能够正常运行

## 本地化

您可以通过两种方式为 Moonlark 贡献本地化语言

### 使用 Crowdin

见 [https://crowdin.com/project/moonlark](https://crowdin.com/project/moonlark)

### 使用 Pull Request

见 [说明](src/plugins/nonebot_plugin_larklang/README.md)
