"""Python lexical/import resolver; dynamic receivers remain diagnostic."""
import ast
from pathlib import Path
from model import Module, Function, digest, uid


def expression(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = expression(node.value)
        return base + '.' + node.attr if base else ''
    return ''


def parse(path: Path, source: Path) -> Module:
    text = path.read_text(encoding='utf-8-sig')
    rel = path.relative_to(source).as_posix()
    tree = ast.parse(text, filename=rel)
    namespace = rel.removesuffix('.py').replace('/', '.')
    if namespace.endswith('.__init__'):
        namespace = namespace[:-9]
    module = Module(rel, 'python', digest(text), text, namespace=namespace, doc=ast.get_docstring(tree) or '')
    owners, lexical = {}, {}
    function_kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

    def definitions(node, scope='', owner='', enclosing=()):
        next_scope, next_owner, next_enclosing = scope, owner, enclosing
        if isinstance(node, ast.ClassDef):
            next_scope = (scope + '.' if scope else '') + node.name
            next_owner = next_scope
        if isinstance(node, function_kinds):
            name = node.name if not isinstance(node, ast.Lambda) else f'<lambda@{node.lineno}:{node.col_offset}>'
            qualified = (scope + '.' if scope else '') + name
            segment = ast.get_source_segment(text, node) or ''
            doc = ast.get_docstring(node) or '' if not isinstance(node, ast.Lambda) else ''
            signature = f'{qualified}({ast.unparse(node.args)})'
            if getattr(node, 'returns', None):
                signature += ' -> ' + ast.unparse(node.returns)
            f = Function(uid('fn', rel + ':' + qualified + ':' + str(node.lineno)), name, qualified, rel, node.lineno, signature, 'python', scope=scope, owner=owner, arity=len(node.args.posonlyargs) + len(node.args.args), doc=doc, source_hash=digest(segment), kind='callback' if isinstance(node, ast.Lambda) else 'method' if owner else 'function')
            owners[node] = f
            lexical[f.id] = enclosing
            module.functions.append(f)
            next_scope, next_enclosing = qualified, (*enclosing, qualified)
        for child in ast.iter_child_nodes(node):
            definitions(child, next_scope, next_owner, next_enclosing)
    definitions(tree)
    entry = Function(uid('fn', rel + ':entry'), '<模块初始化>', '<模块初始化>', rel, 1, rel + ' module initialization', 'python', source_hash=digest(text), kind='entry')

    def import_bindings(node):
        if isinstance(node, ast.Import):
            return {a.asname or a.name.split('.')[0]: a.name if a.asname else a.name.split('.')[0] for a in node.names}
        base = node.module or ''
        if node.level:
            package = namespace.split('.') if path.name == '__init__.py' else namespace.split('.')[:-1]
            base = '.'.join(package[:len(package) - node.level + 1] + ([base] if base else []))
        return {a.asname or a.name: base + '.' + a.name for a in node.names}

    def local_names(node):
        names = set()
        def collect(n):
            if n is not node and isinstance(n, (*function_kinds, ast.ClassDef)):
                return
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                names.add(n.id)
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names.update(import_bindings(n))
            for child in ast.iter_child_nodes(n):
                collect(child)
        collect(node)
        if isinstance(node, function_kinds):
            names.update(a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs)
            names.update(a.arg for a in (node.args.vararg, node.args.kwarg) if a)
        return names

    def global_imports(node):
        if isinstance(node, (*function_kinds, ast.ClassDef)):
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module.imports.update(import_bindings(node))
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            module.types['shadow:' + node.id] = 'global_write'
        for child in ast.iter_child_nodes(node):
            global_imports(child)
    global_imports(tree)

    def visit(node, owner, env, uncertain=False):
        if node in owners:
            owner = owners[node]
            # Captured local values may change before a closure runs.
            inherited = env if lexical[owner.id] else {}
            env = {name: {'kind': 'unknown'} for name in {*inherited, *local_names(node)}}
            uncertain = False
        if isinstance(node, (ast.Import, ast.ImportFrom)) and owner is not entry:
            for name, target in import_bindings(node).items():
                env[name] = {'kind': 'unknown'} if uncertain else {'kind': 'import', 'target': target}
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            env[node.id] = {'kind': 'unknown'}
        if isinstance(node, ast.ExceptHandler) and node.name:
            env[node.name] = {'kind': 'unknown'}
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            local = {**env, **{name: {'kind': 'unknown'} for name in local_names(node)}}
            for child in ast.iter_child_nodes(node):
                visit(child, owner, local, True)
            return
        if isinstance(node, ast.Call):
            call = {'name': expression(node.func), 'arity': len(node.args), 'line': node.lineno, 'text': ast.unparse(node.func), 'environment': dict(env), 'lexical': lexical.get(owner.id, ())}
            owner.calls.append(call)
            for arg in node.args:
                if isinstance(arg, (ast.Name, ast.Attribute, ast.Lambda)):
                    binding = {**call, 'name': expression(arg), 'arity': None}
                    if arg in owners:
                        binding['target'] = owners[arg].id
                    owner.bindings.append(binding)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            value = node.value
            if value:
                visit(value, owner, env, uncertain)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for item in ast.walk(target):
                    if not isinstance(item, ast.Name):
                        continue
                    state = {'kind': 'unknown'}
                    if not uncertain and isinstance(value, ast.Call) and expression(value.func):
                        state = {'kind': 'constructed', 'target': expression(value.func)}
                    elif not uncertain and value in owners:
                        state = {'kind': 'function', 'target': owners[value].id}
                    env[item.id] = state
            return
        if isinstance(node, (ast.AugAssign, ast.Delete)):
            for item in ast.walk(node):
                if isinstance(item, ast.Name) and isinstance(item.ctx, (ast.Store, ast.Del)):
                    env[item.id] = {'kind': 'unknown'}
        branch = uncertain or isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match))
        for child in ast.iter_child_nodes(node):
            visit(child, owner, env, branch)
    visit(tree, entry, {})
    if entry.calls or entry.bindings:
        module.functions.insert(0, entry)
    return module


def resolve(modules, edges, bindings, diagnostics):
    python = [m for m in modules if m.language == 'python']
    symbols, ids = {}, {}
    for m in python:
        for f in m.functions:
            symbols.setdefault(m.namespace + '.' + f.qualified, []).append(f)
            ids[f.id] = f
    for m in python:
        for f in m.functions:
            def target(call):
                if call.get('target'):
                    return [ids[call['target']]]
                name = call['name']
                if not name:
                    return []
                parts = name.split('.')
                environment = call['environment']
                state = environment.get(parts[0])
                if state:
                    if state['kind'] == 'function' and len(parts) == 1:
                        return [ids[state['target']]]
                    if state['kind'] == 'import':
                        full = state['target'] + name[len(parts[0]):]
                        return symbols.get(full, []) or symbols.get(full + '.__init__', [])
                    if state['kind'] != 'constructed' or len(parts) < 2:
                        return []
                    typename = state['target']
                    first = typename.split('.')[0]
                    imported = environment.get(first, {})
                    typename = (imported.get('target') if imported.get('kind') == 'import' else m.imports.get(first, m.namespace + '.' + first)) + typename[len(first):]
                    return symbols.get(typename + '.' + '.'.join(parts[1:]), [])
                if parts[0] in {'self', 'cls'}:
                    return []
                if 'shadow:' + parts[0] in m.types:
                    return []
                if parts[0] in m.imports:
                    fullname = m.imports[parts[0]] + name[len(parts[0]):]
                    return symbols.get(fullname, []) or symbols.get(fullname + '.__init__', [])
                # A class namespace is not a lexical scope for a method body.
                for scope in reversed(('', *call['lexical'])):
                    fullname = '.'.join(p for p in (m.namespace, scope, name) if p)
                    result = symbols.get(fullname, []) or symbols.get(fullname + '.__init__', [])
                    if result:
                        return result
                return []
            for call in f.calls:
                matches = target(call)
                if len(matches) == 1:
                    edges.add((f.id, matches[0].id))
                else:
                    diagnostics.append({'file': m.file, 'line': call['line'], 'function': f.id, 'expression': call.get('text', call['name']), 'reason': 'ambiguous' if matches else 'external_or_dynamic'})
            for call in f.bindings:
                matches = target(call)
                if len(matches) == 1 and matches[0].id != f.id:
                    bindings.add((f.id, matches[0].id))
