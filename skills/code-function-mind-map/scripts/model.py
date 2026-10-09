"""Shared source records and canonical call graph. No renderer-specific IDs."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import hashlib
import json
import fnmatch
import os

EXTENSIONS = {'.py': 'python', '.js': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.mts': 'typescript', '.cts': 'typescript', '.tsx': 'typescript', '.vue': 'vue', '.java': 'java', '.c': 'c', '.h': 'c', '.cc': 'cpp', '.cpp': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp', '.hh': 'cpp', '.hxx': 'cpp', '.go': 'go'}
SKIP = {'.git', 'node_modules', 'dist', 'build', 'target', 'vendor', '.venv', 'venv', '__pycache__', '.runtime', '.tools', '.mypy_cache', '.pytest_cache', 'coverage', '.next', '.artifacts', 'history'}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def uid(kind: str, value: str) -> str:
    return kind + '-' + digest(value)[:24]


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


@dataclass
class Function:
    id: str
    name: str
    qualified: str
    file: str
    line: int
    signature: str
    language: str
    scope: str = ''
    owner: str = ''
    arity: int = 0
    doc: str = ''
    source_hash: str = ''
    kind: str = 'function'
    calls: list[dict] = field(default_factory=list)
    bindings: list[dict] = field(default_factory=list)
    types: dict[str, str] = field(default_factory=dict)


@dataclass
class Module:
    file: str
    language: str
    source_hash: str
    text: str
    functions: list[Function] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)
    namespace: str = ''
    includes: list[str] = field(default_factory=list)
    types: dict[str, str] = field(default_factory=dict)
    doc: str = ''


def scan_files(source: Path, output: Path, excludes: list[str]):
    result = []
    for directory, names, filenames in os.walk(source, followlinks=False):
        base = Path(directory)
        names[:] = sorted(n for n in names if n not in SKIP and n not in {'tests', 'test', '__tests__'} and not (base / n).is_symlink() and (base / n).resolve() != output)
        for name in sorted(filenames):
            path = base / name
            if path.is_symlink() or path.suffix.lower() not in EXTENSIONS:
                continue
            rel = path.relative_to(source).as_posix()
            if name.startswith('test_') or any(token in name for token in ('.test.', '.spec.', '_test.go')) or any(fnmatch.fnmatch(rel, p) for p in excludes):
                continue
            result.append(path)
    return sorted(result)


def records(modules):
    return {f.id: f for m in modules for f in m.functions}


def assemble(modules: list[Module], edges: set[tuple[str, str]], bindings: set[tuple[str, str]], diagnostics: list[dict], source: Path):
    functions = records(modules)
    incoming = {k: 0 for k in functions}
    outgoing = {k: 0 for k in functions}
    for a, b in edges:
        incoming[b] += 1
        outgoing[a] += 1
    nodes = [{'id': 'root', 'text': source.name + ' · 函数调用', 'type': 'root', 'importance': 5, 'recall': '模块有哪些职责，入口调用了哪些函数？'}]
    tree = []
    for m in modules:
        mid = uid('file', m.file)
        nodes.append({'id': mid, 'text': m.file, 'type': 'reference', 'importance': 3, 'file': m.file, 'language': m.language, 'source_hash': m.source_hash, 'doc':m.doc})
        tree.append({'from': 'root', 'to': mid, 'type': 'tree'})
        for f in m.functions:
            data = asdict(f)
            data.pop('calls'); data.pop('bindings'); data.pop('types')
            data.update(text=f.name, type='function', importance=4 if incoming[f.id] + outgoing[f.id] >= 5 else 3, incoming=incoming[f.id], outgoing=outgoing[f.id])
            if data['importance'] >= 4:
                data['recall'] = f'{f.name} 的调用者、目标和失败行为是什么？'
            nodes.append(data)
            tree.append({'from': mid, 'to': f.id, 'type': 'tree'})
    return {'version': 2, 'meta': {'title': source.name + ' 函数调用思维导图', 'language': 'zh-CN', 'source': str(source), 'purpose': '理解函数职责和静态调用关系'}, 'nodes': nodes, 'edges': tree + [{'from': a, 'to': b, 'type': 'depends', 'label': '调用'} for a, b in sorted(edges)], 'bindings': [{'from': a, 'to': b} for a, b in sorted(bindings)], 'diagnostics': diagnostics, 'files': [dict(file=m.file, language=m.language, source_hash=m.source_hash) for m in modules]}
