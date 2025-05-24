# 初始化开发环境

::: tip

这些入门步骤是为想要为 Moonlark 开发一些不那么简单的插件的有一定经验的开发者提供的。如果您想进行的更改十分简单，您不必遵循这些步骤。

:::

## 准备工作

您需要一台电脑用于 Moonlark 开发。无论如何，我们不推荐使用移动设备（如安卓平板）进行开发。

::: warning

因为 Moonlark 最低需要 Python 3.11 环境，所以其无法在 Windows 7 上运行，您可能需要 Windows 8.1、macOS 10.9、Linux 3.6 及更高版本的内核或操作系统。

:::


## 搭建开发环境

1. 确保您的 Python 版本 `>= 3.11`。
2. 安装包管理工具 [Poetry][1]（建议安装 `2.1.0` 及以上的版本）。
3. 克隆仓库并安装依赖，可以使用以下指令：

```bash
git clone https://github.com/Moonlark-Dev/Moonlark
cd Moonlark
poetry install
```

## 配置

将`.env.template` 复制为 `.env` 并在 `.env` 文件中填写相关环境变量。

如果仅为测试使用，您不必填写所有环境变量，需要注意的环境变量有以下几项：

| 变量名           | 类型  | 说明            |
|-----------------|-------|-----------------|
| `BAIDU_API_KEY` | `str` | 百度开放平台的 API KEY，主要提供 LarkUtils 审核接口使用。没有 API KEY 可以留空，但所有审核接口调用都会返回“通过”。 |
| `BAIDU_SECRET_KEY` | `str` | 同上，可留空。 |
| `SQLALCHEMY_DATABASE_URL` | `str` | 数据库地址。建议使用默认值 `sqlite+aiosqlite:///database.db`，其将在 Moonlark 根目录下创建一个 `database.db` 用于储存 Moonlark 运行过程中产生的数据。 |

## 搭建测试环境

> 如果您对您的代码有十足的把握，可以跳过该步骤。

为了测试 Moonlark 的代码，您需要运行一个 OneBot 实现并使其连接到 `ws://localhost:8080/onebot/v11/ws`（默认状态下），我们提供了以下两个参考方案：

- 使用 [NapCat](https://napneko.github.io/guide/start-install): 需要有一个闲置的 QQ 号供 NapCat 登录。同时，您可能需要承担该账号被 TX 冻结的风险。
- 使用 [Matcha](https://github.com/A-kirami/matcha): 目前已知无法显示 Moonlark 发出的图片。

## 继续

[第一个 Moonlark 插件][3]

[1]: https://python-poetry.org/docs/
[3]: first-plugin.md
