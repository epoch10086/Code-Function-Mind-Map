---
name: code-function-mind-map
description: 为源码项目生成或更新函数职责与调用关系思维导图，支持 Python、JS/TS、Vue/React、Java、C/C++ 和 Go，输出单文件 XMind、完整 JSON/Markdown 和双击更新入口。
---

# Code-Function-Mind-Map

使用本技能自己的生成器；不依赖其他技能，也不执行目标项目代码。输出以大字重点函数图帮助阅读，完整调用数据另存。默认中文说明，尊重用户指定的语言和输出目录。

## 生成

1. 确认源码根目录和输出位置。默认输出 `<source>/docs/code-map`；只读取源码，排除依赖、构建、测试和输出目录。不要替用户修改项目依赖。
2. 首次使用运行 `python scripts/setup_runtime.py` 准备独立环境；需要下载依赖，遵守当前工具权限。已安装时跳过联网，使用 `.runtime/python/Scripts/python.exe`（Windows）或 `.runtime/python/bin/python`。
3. 运行 `scripts/code_map.py doctor --source <source>`，再运行 `build --source <source> [--output <output>]`。Python/Node/语言解析器缺失时给出实际错误；不宣称不支持的语言已解析。
4. 阅读生成的 `auxiliary/data/graph.json`、诊断和源码，补充文件职责及重点函数的中文用途。按 [annotations.md](references/annotations.md) 写入 `annotations.json` 后运行 `update --config <output>/mindmap.config.json`。注释或推断必须有源码依据；返回值、异常和性能未知时写明，不编造行为。
5. 运行 `validate --output <output>`；交付主要 XMind、双击更新程序和简短统计。说明可视图只含重点函数，完整关系在 JSON/Markdown。原生客户端未打开时如实写“未验证”。

使用脚本路径时相对于此技能目录定位，不依赖当前工作目录。源路径含中文/空格时逐个参数引用。

## 更新

用户请求更新已有导图时，使用该导图的 `mindmap.config.json`。只替换生成清单中的产物，旧版进入 `history`，失败保留旧版。双击更新离线执行，不调用模型；源摘要变化的人工说明自动失效。需要新解释时重新阅读变化源码并刷新 annotations。

分组、排除和字号可在配置中调整，见 [configuration.md](references/configuration.md)。大项目按模块分页，目录直接到每页；不要添加多级索引或缩小字号来塞入更多函数。

## 分析边界

直接调用必须能唯一解析到项目内定义。回调传参/注册另记，不能当作已执行调用。动态派发、反射、函数指针、重载歧义、宏和未解析 import 进入诊断；不是通过全局同名搜索猜测关系。每种语言具体边界见 [analysis.md](references/analysis.md)。

## 验收

检查 canonical 树无环且全节点可达，调用图可以递归；XMind 工作表、ID、跳转、关系方向、字体和几何；Canvas/导航数量一致。结构和采样曲线检查不能证明 XMind 客户端显示效果，实际打开/保存/重开结果单独记录。
