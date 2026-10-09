"""Dispatch language parsers, combine resolved calls, retain all diagnostics."""
from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
from model import EXTENSIONS, Module, Function, scan_files, assemble
import python_adapter
import tree_adapter


def doctor(source: Path, output: Path, excludes):
    if not source.is_dir():
        raise ValueError('Source directory not found: ' + str(source))
    languages = sorted({EXTENSIONS[p.suffix.lower()] for p in scan_files(source, output, excludes)})
    missing = []
    if any(x in languages for x in ('javascript', 'typescript', 'vue')):
        if not shutil.which('node'):
            missing.append('Node.js 18+')
        skill = Path(__file__).resolve().parents[1]
        if not (skill / 'node_modules/typescript').is_dir() or not (skill / 'node_modules/@vue/compiler-sfc').is_dir():
            missing.append('skill Node dependencies; run scripts/setup_runtime.py')
    for language in languages:
        if language in {'c', 'cpp', 'java', 'go'} and (not importlib.util.find_spec('tree_sitter') or not importlib.util.find_spec('tree_sitter_' + language)):
            missing.append('tree-sitter-' + language + '; run scripts/setup_runtime.py')
    return {'languages': languages, 'missing': missing, 'ready': not missing}


def analyze(source: Path, output: Path, config):
    if not source.is_dir():
        raise ValueError('Source directory not found: ' + str(source))
    checks = doctor(source, output, config.get('exclude', []))
    if checks['missing']:
        raise RuntimeError('Missing dependencies: ' + '; '.join(checks['missing']))
    paths = scan_files(source, output, config.get('exclude', []))
    if not paths:
        raise ValueError('No supported source files found')
    cpp_project = any(EXTENSIONS[p.suffix.lower()] == 'cpp' for p in paths)
    modules, edges, bindings, diagnostics = [], set(), set(), []
    js_files = []
    for path in paths:
        language = EXTENSIONS[path.suffix.lower()]
        if language in {'javascript', 'typescript', 'vue'}:
            js_files.append(path.relative_to(source).as_posix())
        elif language == 'python':
            modules.append(python_adapter.parse(path, source))
        else:
            if path.suffix.lower() == '.h' and cpp_project:
                language = 'cpp'
            modules.append(tree_adapter.parse(path, source, language))
    if js_files:
        response = subprocess.run([shutil.which('node'), str(Path(__file__).with_name('javascript.cjs'))], input=json.dumps({'source': str(source), 'files': js_files}), encoding='utf-8', capture_output=True)
        if response.returncode:
            raise ValueError('JS/TS/Vue parser failed:\n' + response.stderr)
        parsed = json.loads(response.stdout)
        diagnostics.extend(parsed['diagnostics'])
        for data in parsed['modules']:
            functions = [Function(**item) for item in data.pop('functions')]
            modules.append(Module(**data, functions=functions))
            for f in functions:
                edges.update((f.id, x['target']) for x in f.calls)
                bindings.update((f.id, x['target']) for x in f.bindings)
    modules.sort(key=lambda m: m.file)
    python_adapter.resolve(modules, edges, bindings, diagnostics)
    tree_adapter.resolve(modules, edges, bindings, diagnostics)
    return assemble(modules, edges, bindings, diagnostics, source)
