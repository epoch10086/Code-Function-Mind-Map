# 配置和命令

先运行 `scripts/setup_runtime.py`。Windows 使用技能目录下 `.runtime/python/Scripts/python.exe`，macOS/Linux 使用 `.runtime/python/bin/python` 执行 `scripts/code_map.py`。

```text
build --source PROJECT [--output OUTPUT]
update --config OUTPUT/mindmap.config.json
validate --output OUTPUT
doctor --source PROJECT [--output OUTPUT]
```

build 默认输出 `PROJECT/docs/code-map`。update 读取生成目录的配置，后续使用同一命令即可重建。doctor 只检查语言和解析依赖；validate 读取实际生成文件，独立检查包和关系，不修改源码。

`mindmap.config.json` 可编辑：

```json
{
  "version": 1,
  "source": "D:/projects/example",
  "output": "D:/maps/example",
  "exclude": ["generated/*", "legacy/**"],
  "groups": [
    {"pattern": "src/api/*", "title": "API 请求"},
    {"pattern": "src/views/*", "title": "业务页面"}
  ],
  "font_size": 17,
  "lane_gap": 32
}
```

source/output 可使用绝对路径或相对于配置文件所在目录的路径。默认分组按实际源码父目录；groups 按数组顺序首个匹配规则生效。排除使用相对路径 glob，默认排除依赖、构建、测试、导图输出。17pt 是默认，支持 16–18pt；lane_gap 不低于 32 像素。分页上限固定为 24 个函数和 40 条可视调用（含短引用），保留可读性。

输出目录必须专用于本导图。已有同名且未登记在 `.generated-files.json` 中的文件不会被覆盖。用户新文件不进入清理范围；annotations/config 为可编辑的受管文件，更新读取后保留其设置，旧版仍有备份。

Windows 双击 `update_mindmap.cmd`；测试时可以传 `--no-pause`。启动器优先寻找当前 `CODEX_HOME/skills/code-function-mind-map`，否则使用配置记录的技能位置。移到另一台机器后先安装技能及其依赖，再调整源码/输出路径。程序不会自动联网恢复依赖。

`.code-map.lock` 防止重复更新。如进程被强制终止，先确认没有更新进程仍在运行，再移除该输出目录中的锁文件。正常失败会自动释放锁。

CLI 成功返回 0，解析/依赖/校验/写入失败返回非 0。遇到语法错误整次更新失败，保留旧导图，不生成悄悄缺文件的“成功”结果。
