"""Java/C/C++/Go syntax adapters with bounded, explicit symbol resolution."""
from pathlib import Path
import importlib
import re
from model import Module, Function, digest, uid


def descendants(node):
    yield node
    for child in node.named_children:
        yield from descendants(child)


def value(node, code):
    return code[node.start_byte:node.end_byte].decode('utf-8') if node else ''


def field(node, name, code):
    return value(node.child_by_field_name(name), code)


def normalized(name):
    return re.sub(r'[<>].*', '', name.replace('::', '.').strip('*& '))


def declaration_name(node, code):
    if not node:
        return ''
    if node.type in {'identifier', 'field_identifier', 'qualified_identifier', 'operator_name', 'destructor_name'}:
        return normalized(value(node, code))
    return declaration_name(node.child_by_field_name('declarator'), code)


def parse(path: Path, source: Path, language: str) -> Module:
    from tree_sitter import Language, Parser
    grammar = importlib.import_module('tree_sitter_' + language)
    text = path.read_text(encoding='utf-8-sig')
    code = text.encode('utf-8')
    tree = Parser(Language(grammar.language())).parse(code)
    rel = path.relative_to(source).as_posix()
    if tree.root_node.has_error:
        error = next((n for n in descendants(tree.root_node) if n.type == 'ERROR' or n.is_missing), tree.root_node)
        raise ValueError(f'{rel}:{error.start_point.row + 1}: syntax error ({error.type})')
    module = Module(rel, language, digest(text), text)
    header = re.match(r'\s*(/\*.*?\*/|(?://[^\n]*\n)+)', text, re.DOTALL)
    module.doc = header[1] if header else ''
    if language == 'go':
        modfile = source / 'go.mod'
        prefix = re.search(r'(?m)^module\s+(\S+)', modfile.read_text(encoding='utf-8')) if modfile.exists() else None
        parent = path.parent.relative_to(source).as_posix()
        module.namespace = (prefix[1] if prefix else '<local>') + ('/' + parent if parent != '.' else '')
    nodes = list(descendants(tree.root_node))
    for node in nodes:
        if node.type == 'package_declaration' and language == 'java':
            module.namespace = value(node, code).removeprefix('package').strip(' ;\r\n')
        if node.type == 'import_declaration' and language == 'java':
            target = value(node, code).removeprefix('import').removeprefix(' static').strip(' ;\r\n')
            module.imports[target.split('.')[-1]] = target
        if node.type == 'import_spec' and language == 'go':
            target = field(node, 'path', code).strip('"`')
            alias = field(node, 'name', code) or target.rsplit('/', 1)[-1]
            module.imports[alias] = target
        if node.type == 'preproc_include':
            target = field(node, 'path', code).strip('"<>')
            module.includes.append(target)
        if node.type in {'preproc_function_def', 'preproc_def'}:
            module.types['macro:' + field(node, 'name', code)] = 'macro'
    function_nodes = {}

    def visit(node, scope='', owner=''):
        next_scope, next_owner = scope, owner
        if node.type in {'class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration', 'class_specifier', 'struct_specifier', 'namespace_definition'}:
            name = field(node, 'name', code)
            if name:
                next_scope = '.'.join(x for x in (scope, name) if x)
                if node.type != 'namespace_definition':
                    next_owner = next_scope
        body = node.child_by_field_name('body')
        anonymous = node.type in {'lambda_expression', 'func_literal'}
        if (node.type in {'function_definition', 'function_declaration', 'method_declaration', 'constructor_declaration', 'compact_constructor_declaration'} or anonymous) and body:
            name = f'<callback@{node.start_point.row + 1}:{node.start_point.column}>' if anonymous else field(node, 'name', code) or declaration_name(node.child_by_field_name('declarator'), code)
            local_owner = owner
            parameters = node.child_by_field_name('parameters')
            if language in {'c', 'cpp'}:
                declarator = node.child_by_field_name('declarator')
                while declarator and declarator.type not in {'function_declarator','abstract_function_declarator'}:
                    declarator = declarator.child_by_field_name('declarator')
                parameters = declarator.child_by_field_name('parameters') if declarator else None
            if language == 'go' and node.type == 'method_declaration':
                receiver = node.child_by_field_name('receiver')
                param = receiver.named_children[0] if receiver and receiver.named_children else None
                local_owner = normalized(field(param, 'type', code)) if param else ''
                scope = local_owner
            qualified = '.'.join(x for x in (scope, name if anonymous else normalized(name)) if x)
            if '.' in name and scope and name.startswith(scope + '.'):
                qualified = normalized(name)
            if language == 'cpp' and '.' in qualified and not local_owner:
                local_owner = qualified.rsplit('.', 1)[0]
            preceding = text.splitlines()[max(0, node.start_point.row - 6):node.start_point.row]
            doc = '\n'.join(line.strip(' /\t*') for line in preceding if line.strip().startswith(('//', '*', '/*')))
            params = parameters.named_children if parameters else []
            f = Function(uid('fn', rel + ':' + str(node.start_byte)), name.split('.')[-1], qualified, rel, node.start_point.row + 1, code[node.start_byte:body.start_byte].decode('utf-8').strip(), language, scope=scope, owner=local_owner, arity=sum(1 for p in params if p.type not in {'comment'} and value(p, code) != 'void'), doc=doc, source_hash=digest(doc + '\n' + value(node, code)), kind='callback' if anonymous else 'constructor' if 'constructor' in node.type else 'method' if local_owner else 'function')
            for param in params:
                pname = field(param, 'name', code) or declaration_name(param.child_by_field_name('declarator'), code)
                if pname:
                    f.types[pname] = normalized(field(param, 'type', code))
            if language == 'go' and local_owner and param:
                receiver = node.child_by_field_name('receiver').named_children[0]
                f.types[field(receiver, 'name', code)] = local_owner
            function_nodes[node.id] = f
            module.functions.append(f)
        if node.type in {'declaration', 'field_declaration', 'local_variable_declaration'}:
            typ = normalized(field(node, 'type', code))
            for item in node.named_children:
                if item.type == 'function_declarator':
                    module.types['declaration:' + declaration_name(item, code)] = typ
                if item.type == 'variable_declarator' and node.type == 'field_declaration':
                    module.types[(owner + '.' if owner else '') + field(item, 'name', code)] = typ
        for child in node.named_children:
            visit(child, next_scope, next_owner)
    visit(tree.root_node)
    entry = Function(uid('fn', rel + ':entry'), '<模块初始化>', '<模块初始化>', rel, 1, rel + ' module initialization', language, source_hash=digest(text), kind='entry')

    def collect(node, function=None, uncertain=False):
        if node.id in function_nodes:
            function = function_nodes[node.id]
            uncertain = False
        if function:
            if node.type in {'local_variable_declaration', 'declaration'}:
                typ = normalized(field(node, 'type', code))
                for item in node.named_children:
                    name = field(item, 'name', code) if item.type == 'variable_declarator' else declaration_name(item, code)
                    if name and typ:
                        function.types[name] = typ
                        initializer = item.child_by_field_name('value')
                        function.types.pop('callback:' + name, None)
                        if initializer and initializer.id in function_nodes and not uncertain:
                            function.types['callback:' + name] = function_nodes[initializer.id].id
                        function.types.pop('exact:' + name, None)
                        anonymous_class = initializer and any(child.type == 'class_body' for child in initializer.named_children)
                        if language == 'java' and not uncertain and initializer and initializer.type == 'object_creation_expression' and not anonymous_class:
                            function.types[name] = normalized(field(initializer, 'type', code))
                            function.types['exact:' + name] = 'constructed'
            if node.type in {'assignment_expression', 'assignment_statement', 'update_expression'}:
                target = node.child_by_field_name('left') or node.child_by_field_name('operand')
                for item in descendants(target) if target else []:
                    if item.type == 'identifier':
                        function.types.pop(value(item, code), None)
                        function.types.pop('exact:' + value(item, code), None)
                        function.types.pop('callback:' + value(item, code), None)
            if node.type == 'short_var_declaration':
                left, right = node.child_by_field_name('left'), node.child_by_field_name('right')
                if left and right and len(left.named_children) == len(right.named_children):
                    for a, b in zip(left.named_children, right.named_children):
                        if b.type == 'composite_literal':
                            function.types[value(a, code)] = normalized(field(b, 'type', code))
                        elif b.id in function_nodes and not uncertain:
                            function.types['callback:' + value(a, code)] = function_nodes[b.id].id
            if node.type in {'method_invocation', 'call_expression', 'object_creation_expression', 'new_expression'}:
                arguments = node.child_by_field_name('arguments')
                arity = len([n for n in arguments.named_children if n.type != 'comment']) if arguments else 0
                if node.type == 'method_invocation':
                    receiver = field(node, 'object', code)
                    name = (receiver + '.' if receiver else '') + field(node, 'name', code)
                elif node.type in {'object_creation_expression','new_expression'}:
                    name = field(node, 'type', code) + '.#constructor'
                else:
                    name = field(node, 'function', code).replace('->', '.').replace('::', '.')
                call = {'name': name, 'arity': arity, 'line': node.start_point.row + 1, 'types': dict(function.types)}
                function.calls.append(call)
                for argument in arguments.named_children if arguments else []:
                    if argument.id in function_nodes:
                        function.bindings.append(dict(target=function_nodes[argument.id].id, line=call['line']))
                    elif argument.type in {'identifier', 'scoped_identifier', 'qualified_identifier', 'method_reference'}:
                        function.bindings.append(dict(name=value(argument, code).replace('::','.'), arity=None, line=call['line'], types=dict(function.types)))
        branch = uncertain or node.type in {'if_statement','for_statement','enhanced_for_statement','while_statement','do_statement','try_statement','switch_statement','switch_expression','for_range_loop'}
        for child in node.named_children:
            collect(child, function, branch)
    collect(tree.root_node,entry)
    if entry.calls:
        module.functions.insert(0,entry)
    return module


def resolve(modules, edges, bindings, diagnostics):
    native = [m for m in modules if m.language in {'java', 'c', 'cpp', 'go'}]
    by_file = {m.file: m for m in native}
    symbols = {}
    functions = {f.id:f for m in native for f in m.functions}
    for m in native:
        for f in m.functions:
            key = (m.language, m.namespace, f.qualified)
            symbols.setdefault(key, []).append(f)

    def included(module):
        result = {module.file}
        def visit(m):
            for include in m.includes:
                candidates = {(Path(m.file).parent / include).as_posix(), include}
                for path in candidates:
                    if path in by_file and path not in result:
                        result.add(path); visit(by_file[path])
        visit(module)
        return result

    for m in native:
        accessible = included(m)
        for f in m.functions:
            def targets(call):
                if call.get('target'):
                    return [functions[call['target']]]
                name = normalized(call['name'])
                types = call.get('types', {})
                if 'callback:' + call['name'] in types:
                    return [functions[types['callback:' + call['name']]]]
                if not name or 'macro:' + name in m.types:
                    return []
                if m.language == 'java':
                    parts = name.split('.')
                    if name.endswith('.#constructor'):
                        typ = name.removesuffix('.#constructor')
                        full = m.imports.get(typ, (m.namespace + '.' if m.namespace else '') + typ)
                        package, _, cls = full.rpartition('.')
                        result = symbols.get(('java', package, cls + '.' + cls), [])
                    elif len(parts) > 1:
                        obj, method = '.'.join(parts[:-1]), parts[-1]
                        known_class = any(lang=='java' and namespace==m.namespace and qualified.startswith(obj+'.') for lang,namespace,qualified in symbols)
                        typ = f.owner if obj == 'this' else types.get(obj) or m.types.get(f.owner + '.' + obj) or (obj if obj in m.imports or obj == f.owner or known_class else '')
                        if not typ:
                            return []
                        full = m.imports.get(typ, (m.namespace + '.' if m.namespace else '') + typ)
                        package, _, cls = full.rpartition('.')
                        result = symbols.get(('java', package, cls + '.' + method), [])
                    else:
                        result = symbols.get(('java', m.namespace, f.owner + '.' + name), [])
                        if not result and name in m.imports:
                            full = m.imports[name]; package, cls, method = full.rsplit('.', 2)
                            result = symbols.get(('java', package, cls + '.' + method), [])
                elif m.language == 'go':
                    parts = name.split('.')
                    namespace = m.namespace
                    if len(parts) == 2 and parts[0] in m.imports:
                        namespace, name = m.imports[parts[0]], parts[1]
                    elif len(parts) == 2 and parts[0] in types:
                        name = types[parts[0]] + '.' + parts[1]
                    result = symbols.get(('go', namespace, name), [])
                else:
                    constructor = name.endswith('.#constructor')
                    if constructor:
                        typ=name.removesuffix('.#constructor')
                        name=typ+'.'+typ.rsplit('.',1)[-1]
                    parts = name.split('.')
                    if len(parts) == 2 and parts[0] in types:
                        name = types[parts[0]] + '.' + parts[1]
                    elif name.startswith('this.') and f.owner:
                        name = f.owner + name[4:]
                    result = []
                    scope = f.scope.split('.') if f.scope else []
                    for length in range(len(scope), -1, -1):
                        qualified = '.'.join([*scope[:length], name])
                        candidates = [item for lang in ('c', 'cpp') for item in symbols.get((lang, '', qualified), [])]
                        candidates = [x for x in candidates if x.file==m.file or not re.search(r'\bstatic\b',x.signature)]
                        local = [x for x in candidates if x.file in accessible]
                        if local:
                            result = local; break
                        declared = any('declaration:' + qualified in by_file[path].types for path in accessible)
                        if declared:
                            result = candidates; break
                if call['arity'] is not None:
                    result = [x for x in result if x.arity == call['arity']]
                if m.language == 'java' and not name.endswith('.#constructor'):
                    receiver=call['name'].rsplit('.',1)[0] if '.' in call['name'] else 'this'
                    exact='exact:'+receiver in types
                    result=[x for x in result if exact or re.search(r'\b(static|private|final)\b',x.signature)]
                if m.language == 'cpp':
                    result=[x for x in result if not re.search(r'\bvirtual\b',x.signature)]
                return result
            for call in f.calls:
                matches = targets(call)
                if len(matches) == 1:
                    edges.add((f.id, matches[0].id))
                else:
                    diagnostics.append({'file': m.file, 'line': call['line'], 'function': f.id, 'expression': call['name'], 'reason': 'ambiguous' if matches else 'external_or_dynamic'})
            for call in f.bindings:
                matches = targets(call)
                if len(matches) == 1:
                    bindings.add((f.id, matches[0].id))
