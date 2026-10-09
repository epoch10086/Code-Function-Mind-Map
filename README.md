# Code-Function-Mind-Map

把源码变成直观的函数调用思维导图：单文件 XMind、大字重点函数、按模块分页、最多两次跳转。完整函数及调用另存 JSON/Markdown，代码变化后可双击更新。

支持 Python、JavaScript、TypeScript、Vue、React（JSX/TSX）、Java、C/C++、Go。解析源码，不运行项目，不修改项目依赖。静态无法确认的调用单独报告。

## 安装为 Codex Skill

需要 Python 3.11+、Node.js 18+ 和 npm。首次安装联网下载到技能自己的环境，后续生成离线运行。

```powershell
py -3.11 scripts/install_skill.py
```

安装到 `CODEX_HOME/skills/code-function-mind-map`（未设置时为用户目录 `.codex/skills`）。安装后在新的 Codex 聊天中调用：

> 使用 `$code-function-mind-map`，为当前项目生成函数调用思维导图。

也可以指定源码和输出位置。默认输出是项目的 `docs/code-map`。技能会阅读源码补充中文说明；独立 CLI 只使用已有说明和源码文档。

## 直接运行

在仓库技能目录运行 `python scripts/setup_runtime.py` 准备环境，再使用该目录的 `.runtime/python/Scripts/python.exe`（Windows）或 `.runtime/python/bin/python`（macOS/Linux）：

```text
scripts/code_map.py build --source PROJECT [--output OUTPUT]
scripts/code_map.py update --config OUTPUT/mindmap.config.json
scripts/code_map.py validate --output OUTPUT
scripts/code_map.py doctor --source PROJECT
```

Windows 双击生成目录的 `update_mindmap.cmd` 更新。主导图为 `code-function-call-mindmap.xmind`；XMind 2021+ 打开。目录直接到模块页，引用直接到目标函数，普通函数在备注、JSON 和 Markdown 中完整保留。

源码变更导致旧中文说明失效时，双击更新会标记待刷新；再次调用技能可阅读源码更新说明。失败不会覆盖旧版；成功更新前的产物存于 `history`，用户自建文件不会清理。

## 开发和验收

```powershell
skills/code-function-mind-map/.runtime/python/Scripts/python.exe -m unittest discover -s tests -v
```

包结构、链接、字号、节点和采样曲线检查不代表原生 XMind 渲染已经验证。实际打开、保存、关闭、重开需单独验收。

技能说明和语言边界见 [SKILL.md](skills/code-function-mind-map/SKILL.md)。

本次测试、只读前端回归和客户端验收状态见 [验收记录](docs/validation.md)，两个独立审查结果见 [审查记录](docs/review.md)。Windows 可用 `scripts/check_layout.ps1 -Output OUTPUT` 测量文字布局；此检查不代替 XMind 客户端验收。

本次 agent 无法写入原仓库受保护的 `.git`，实现已保留在 Epoch 工作区。交付补丁在 `.artifacts/epoch-implementation.patch`；在本机双击 `scripts/complete_epoch_commit.cmd` 可核对基线后完成本地提交，不会推送。这个程序仅用于本次 Epoch 交付，日常更新导图使用生成目录中的 `update_mindmap.cmd`。
