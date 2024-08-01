# 初始化开发环境

:::tip

无论如何，我们不推荐使用移动设备（如安卓平板）进行开发。

:::

## 准备工作

您需要一台电脑用于 Moonlark 开发。

::: warning

因为 Moonlark 最低需要 Python 3.11 环境，所以其无法在 Windows 7 上运行，您可能需要 Windows 8.1、macOS 10.9、Linux 3.6 及更高版本的内核或操作系统。

:::


## 搭建开发环境

1. 确保您的 Python3 版本 `>= 3.11`。
2. 安装 [Poetry][1]（建议安装 `1.8.2` 及以上的版本）
3. 克隆仓库并安装依赖

```bash
git clone https://github.com/Moonlark-Dev/Moonlark
cd Moonlark
poetry install
```

## 配置

将`.env.template` 复制为 `.env` 并在 `.env` 文件中填写相关环境变量。

> 如果您为 [IT Craft Development Team][2] 成员，可以尝试向我们申请获得部分 Moonlark 使用的环境变量值。

## 继续

[第一个 Moonlark 插件][3]

[1]: https://python-poetry.org/docs/
[2]: https://join.itcdt.top
[3]: first-plugin.md
