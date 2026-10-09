"""Build/update/validate a portable code-call workbook. Builds never use network."""
from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime
from model import load, write
from analyzer import analyze, doctor
from render import Workbook, enrich, markdown, json_bytes
from validation import validate_output

sys.dont_write_bytecode=True
SKILL=Path(__file__).resolve().parents[1]

BOOTSTRAP='''# Generated portable updater: project code is never executed.
from pathlib import Path
import json, os, sys, subprocess
root = Path(__file__).resolve().parents[1]
config = root / "mindmap.config.json"
data = json.loads(config.read_text(encoding="utf-8"))
home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
candidates = [home / "skills" / "code-function-mind-map", Path(data["skill_path"])]
for skill in candidates:
    script = skill / "scripts" / "code_map.py"
    python = skill / ".runtime" / "python" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if script.is_file() and python.is_file():
        result = subprocess.run([str(python), str(script), "update", "--config", str(config)])
        raise SystemExit(result.returncode)
raise SystemExit("Skill runtime not found. Install code-function-mind-map and run setup_runtime.py.")
'''
CMD='''@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Update code function mindmap
echo Please close XMind before updating.
where py.exe >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0auxiliary\\update.py"
) else (
  python "%~dp0auxiliary\\update.py"
)
set "CODE_MAP_RESULT=%ERRORLEVEL%"
if "%CODE_MAP_RESULT%"=="0" (
  echo [DONE] code-function-call-mindmap.xmind is updated.
) else (
  echo [FAILED] See the error above. The previous version was kept.
)
if /i not "%~1"=="--no-pause" pause
exit /b %CODE_MAP_RESULT%
'''


@contextmanager
def output_lock(output):
    lock=output/'.code-map.lock'
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        with os.fdopen(descriptor,'w') as f:
            f.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def safe_member(root, name):
    target=(root/name).resolve()
    if not target.is_relative_to(root.resolve()) or target==root.resolve() or Path(name).is_absolute():
        raise ValueError('Invalid generated file path: '+name)
    return target


def install_snapshot(stage, output, artifact_names):
    manifest=output/'.generated-files.json'
    previous=load(manifest)['files'] if manifest.exists() else []
    for name in artifact_names:
        destination=safe_member(output,name)
        if destination.exists() and name not in previous:
            raise ValueError('Refusing to overwrite an unowned file: '+str(destination))
    for name in previous:
        safe_member(output,name)
    backup=output/'history'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    moved=[];installed=[]
    try:
        for name in previous:
            original=safe_member(output,name)
            if original.is_file():
                target=backup/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(original,target)
                moved.append(name)
        for name in artifact_names:
            destination=safe_member(output,name);destination.parent.mkdir(parents=True,exist_ok=True)
            os.replace(stage/name,destination);installed.append(name)
        for name in previous:
            if name not in artifact_names:
                safe_member(output,name).unlink(missing_ok=True)
    except BaseException:
        for name in installed:
            destination=safe_member(output,name)
            if name not in moved:
                destination.unlink(missing_ok=True)
        for name in moved:
            original=safe_member(output,name);original.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(backup/name,original)
        raise
    return str(backup) if moved else None


def readme(report):
    return f'''# 代码函数调用思维导图

打开 `code-function-call-mindmap.xmind`。目录直接进入模块页，目标引用直接到函数；最多两次跳转。卡片使用 17pt 字号，只显示重点函数和关键关系。

## 文件用途

| 文件 | 用途 |
|---|---|
| code-function-call-mindmap.xmind | 日常阅读的唯一主导图 |
| update_mindmap.cmd | Windows 双击更新，先关闭 XMind |
| mindmap.config.json | 源码路径、排除规则、分组和显示参数 |
| annotations.json | 按源码摘要保存的中文说明；可人工编辑 |
| auxiliary/data/graph.json | 完整函数、调用、回调注册及未解析诊断 |
| auxiliary/data/navigation-index.json | 可视函数、主题、链接及几何数据 |
| auxiliary/data/verification-report.json | 结构与几何验收；客户端检查单独记录 |
| auxiliary/canvas | 各页 Canvas |
| auxiliary/markdown/functions-and-calls.md | 全部函数、用途、签名和调用清单 |
| auxiliary/previews | 几何 SVG 预览，不等同于原生客户端显示 |
| history | 更新前的生成文件备份 |

## 代码修改后更新

Windows 双击 `update_mindmap.cmd`，看到 `[DONE]` 后重新打开 XMind。
其他系统运行 `python3 auxiliary/update.py`。更新离线运行，不执行项目代码，不修改项目依赖。失败保留上一版本。
中文补充说明在源码摘要变化后失效；重新调用 `$code-function-mind-map` 可阅读新源码补充说明。

完整扫描：{report['files']} 文件、{report['functions']} 函数/初始化节点、{report['canonical_relationships']} 调用。可视：{report['visible_functions']} 重点函数、{report['sheets']} 工作表。
结构与采样曲线检查通过。原生 XMind 打开、保存、重开未验证。
'''


def build(source,output,config=None):
    source=source.resolve();output=output.resolve()
    if not source.is_dir() or source.is_relative_to(output):
        raise ValueError('Output must be a dedicated directory, not source or a parent of source')
    config=dict(config or {})
    config.update(version=1,source=str(source),output=str(output),skill_path=str(SKILL))
    config.setdefault('exclude',[]);config.setdefault('groups',[])
    config.setdefault('font_size',17);config.setdefault('lane_gap',32)
    if config['font_size'] not in (16,17,18) or config['lane_gap']<32:
        raise ValueError('font_size must be 16..18; lane_gap must be >=32')
    output.mkdir(parents=True,exist_ok=True)
    with output_lock(output):
        graph=analyze(source,output,config)
        annotations=load(output/'annotations.json') if (output/'annotations.json').exists() else {'files':{},'functions':{}}
        enrich(graph,annotations)
        workbook=Workbook(graph,config).build()
        artifacts=workbook.artifacts()
        artifacts.update({'auxiliary/data/graph.json':json_bytes(graph),'auxiliary/markdown/functions-and-calls.md':markdown(graph,workbook),'mindmap.config.json':json_bytes(config),'annotations.json':json_bytes(annotations),'auxiliary/update.py':BOOTSTRAP.encode('utf-8'),'update_mindmap.cmd':CMD.replace('\n','\r\n').encode('ascii')})
        stage=output/('.stage-'+uuid.uuid4().hex)
        stage.mkdir()
        try:
            for name,data in artifacts.items():
                destination=stage/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
            report=validate_output(stage)
            artifacts['auxiliary/data/verification-report.json']=json_bytes(report)
            artifacts['README.md']=readme(report).encode('utf-8')
            artifacts['.generated-files.json']=json_bytes({'version':1,'files':sorted([*artifacts,'.generated-files.json'])})
            for name in ('auxiliary/data/verification-report.json','README.md','.generated-files.json'):
                destination=stage/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(artifacts[name])
            report['backup']=install_snapshot(stage,output,sorted(artifacts))
        finally:
            # The exact generated staging directory is the only recursive cleanup target.
            if stage.parent==output and stage.name.startswith('.stage-'):
                shutil.rmtree(stage)
    return {**report,'main_file':str(output/'code-function-call-mindmap.xmind')}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('build','doctor'):
        command=sub.add_parser(name);command.add_argument('--source',type=Path,required=True);command.add_argument('--output',type=Path)
    sub.add_parser('update').add_argument('--config',type=Path,required=True)
    sub.add_parser('validate').add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.command=='update':
        config=load(args.config)
        source=Path(config['source']);output=Path(config['output'])
        if not source.is_absolute():source=args.config.resolve().parent/source
        if not output.is_absolute():output=args.config.resolve().parent/output
        result=build(source,output,config)
    elif args.command=='validate':
        result=validate_output(args.output.resolve())
    else:
        source=args.source.resolve();output=(args.output or source/'docs/code-map').resolve()
        result=build(source,output) if args.command=='build' else doctor(source,output,[])
        if args.command=='doctor' and not result['ready']:
            print(json.dumps(result,ensure_ascii=False,indent=2));return 1
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except (ValueError,RuntimeError,OSError,KeyError,SyntaxError) as error:
        print('[ERROR] '+str(error),file=sys.stderr);raise SystemExit(1)
