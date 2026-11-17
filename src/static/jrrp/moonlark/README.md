# jrrp 人品卡插画

`a.png` ~ `f.png` 由一整张六格 Moonlark 插画裁出，对应签到插件
`nonebot_plugin_sign` 的 a~f 六档运势（>80 / 61-80 / 41-60 / 21-40 / 1-20 / 0）。
每一格在原图里自带圆角白边，裁切时先按格向内缩 1px，再套半径 17px 的圆角遮罩，
所以这里的 PNG 四角是透明的，放进人品卡后再由卡片自己的圆角遮罩收边。

替换插画时保持同样的分格与圆角处理即可；卡片代码见
`src/plugins/nonebot_plugin_jrrp/card.py`。
