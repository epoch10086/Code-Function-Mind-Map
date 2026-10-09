# 验收记录

日期：2026-10-09。运行环境为 Windows、Python 3.11、Node.js；Python/Node 依赖安装在仓库技能和本机技能各自的隔离目录。锁定版本见技能 requirements.txt 与 package-lock.json。

## 自动验证

`python -m unittest discover -s tests -v`：28 项通过。覆盖 Python、JS/TS/JSX/TSX/Vue、Java、C/C++、Go；包括跨文件、别名、方法/构造、回调与直接调用分离、匿名函数、自递归、同名和重载歧义、动态接收者、重新绑定与文档变更。

更新验证包括中文和空格路径、依赖缺失、语法失败、源码新增修改删除、重复更新、并发锁、用户文件保留及模拟写入失败后的全量恢复。bootstrap 会等待生成器并传递退出码；旧导图不会因语法错误被覆盖。

skill-creator 的 quick_validate.py 在仓库和已安装技能目录均通过。Windows 的默认 GBK 与中文技能文件不一致，因此校验器使用 `-X utf8` 运行。

## 本机安装验证

安装位置为 `C:/Users/Hzh19/.codex/skills/code-function-mind-map`。从此位置独立运行 build、update、validate，输出到隔离的 `.artifacts/installed smoke 中文`：7 文件、10 函数、12 条调用、4 工作表；校验通过。

Windows `update_mindmap.cmd --no-pause` 实测成功，生成器结束后才显示 `[DONE]`，退出码为 0。首次依赖准备后 build/update 不联网，也不执行目标项目代码。

## 原前端项目只读回归

源码为 `G:/Git/AI预测防护/new-AI-project/software/Front-end`，输出为本仓库 `.artifacts/frontend-regression`；未覆盖 `G:/Xmind/git` 的既有导图。扫描的 68 文件逐一比较 SHA-256，前后相同。

| 指标 | 本次结果 |
|---|---:|
| 全部函数/初始化节点 | 608 |
| 确认调用 | 444 |
| 重点函数 | 142 |
| 隐藏函数 | 466 |
| 工作表，含目录 | 23 |
| XMind 主题 | 291 |
| 可视箭头 | 25 |
| 短目标引用 | 67 |
| 内部跳转 | 111 |
| 未确认调用诊断 | 1273 |

诊断包括项目外库调用，不表示这些表达式不存在。相对旧导图的 600 函数、471 调用：增加 8 个模块初始化节点，旧函数没有丢失；增加 3 条 Python 初始化到入口的调用；30 条不够确定的调用转入诊断，净减少 27 条。转入诊断的关系包括 Python self 动态派发、TypeScript 接收者运行时类型、defineStore 等 wrapper 返回值及条件函数表达式。详细新增/删除列表在隔离输出 `regression-evidence.json`。

## 导图可读性检查

验证实际 XMind ZIP、默认目录、全局 ID、跳转的具体目标、Canvas/导航/完整关系一致性、17pt 卡片、每页 24 个函数和 40 条箭头加引用上限、节点矩形及采样曲线。相反方向箭头使用分开的控制点，曲线经过正文或距离过长时回退短引用。

最终增量审查发现竞争的入/出边可能让互反曲线使用同一路径。已在生成前比较既有路径及其反向，重合时回退短引用；五函数九边的审查复现已加入自动测试，完整可视关系仍为九条。

`scripts/check_layout.ps1` 用 Windows Microsoft YaHei 96dpi 测量全部 291 主题，文字溢出为 0。卡片不扩大，长名称采用保留首尾的缩略，完整内容在备注。已检查 API 几何预览，预览属于生成器布局验收。

原生 XMind 客户端打开、保存、关闭、重开：**未验证**。结构、字体测量和预览没有被当作原生客户端验收。需在 XMind 2021+ 打开测试产物，重点检查 API、告警和实时状态页。

## 本地提交状态

源码已保留在指定原仓库 Epoch 工作区。隔离 Epoch 副本有可审查本地提交，交付补丁和 Git bundle 保存在 `.artifacts`，运行环境及生成导图均不提交。

原仓库 `.git` 受到宿主系统的显式 ACL 写入拒绝，agent 无法创建 index.lock，原仓库本地提交尚未完成。已提供 `scripts/complete_epoch_commit.cmd`：用户在本机双击后，它先核对 Epoch、固定基线和空暂存区，再仅暂存交付补丁并完成本地 commit，不 push、不改工作树或 ACL。若分支/基线/暂存区已变化则停止，保留现场。
