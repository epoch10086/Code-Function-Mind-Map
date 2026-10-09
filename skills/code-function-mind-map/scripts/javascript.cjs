'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const ts = require('typescript');
const { parse: parseVue } = require('@vue/compiler-sfc');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = path.resolve(request.source);
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const uid = (kind, value) => kind + '-' + hash(value).slice(0, 24);
const normalize = value => path.resolve(value).replaceAll('\\', '/');
const contents = new Map(), physical = new Map(), originals = new Map();
for (const rel of request.files) {
  const real = path.join(source, rel);
  const virtual = rel.endsWith('.vue') ? real + '.ts' : real;
  let text = fs.readFileSync(real, 'utf8');
  originals.set(rel, text);
  if (rel.endsWith('.vue')) {
    const parsed = parseVue(text, { filename: real });
    if (parsed.errors.length) throw new Error('Vue parse error: ' + rel + ': ' + parsed.errors[0]);
    const blocks = [parsed.descriptor.script, parsed.descriptor.scriptSetup].filter(Boolean);
    const ranges = blocks.map(b => [b.loc.start.offset, b.loc.end.offset]);
    text = text.split('').map((c, i) => ranges.some(([a, b]) => i >= a && i < b) || /\s/.test(c) ? c : ' ').join('');
  }
  contents.set(normalize(virtual), text);
  physical.set(normalize(virtual), rel);
}
let options = { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler, allowJs: true, checkJs: true, skipLibCheck: true, jsx: ts.JsxEmit.Preserve };
for (const name of ['tsconfig.json', 'tsconfig.app.json', 'jsconfig.json']) {
  const config = path.join(source, name);
  if (fs.existsSync(config)) {
    const read = ts.readConfigFile(config, ts.sys.readFile);
    if (read.error) throw new Error('Invalid config: ' + config);
    const parsed = ts.parseJsonConfigFileContent(read.config, ts.sys, source);
    options = { ...options, ...parsed.options, allowJs: true, noEmit: true };
  }
}
const host = ts.createCompilerHost(options);
const read = host.readFile.bind(host), exists = host.fileExists.bind(host), get = host.getSourceFile.bind(host);
host.readFile = f => contents.get(normalize(f)) ?? read(f);
host.fileExists = f => contents.has(normalize(f)) || exists(f);
host.getSourceFile = (f, version, error, fresh) => contents.has(normalize(f)) ? ts.createSourceFile(f, contents.get(normalize(f)), version, true, /\.(jsx|tsx)$/.test(f) ? ts.ScriptKind.TSX : /\.[cm]?js$/.test(f) ? ts.ScriptKind.JS : ts.ScriptKind.TS) : get(f, version, error, fresh);
host.resolveModuleNames = (names, containing) => names.map(name => {
  let resolved = ts.resolveModuleName(name, containing, options, host).resolvedModule;
  if (resolved && contents.has(normalize(resolved.resolvedFileName))) return resolved;
  const bases = [];
  if (name.startsWith('.')) bases.push(path.resolve(path.dirname(containing), name));
  for (const [pattern, values] of Object.entries(options.paths || {})) {
    const parts = pattern.split('*');
    if (name.startsWith(parts[0]) && (!parts[1] || name.endsWith(parts[1]))) {
      const wildcard = name.slice(parts[0].length, parts[1] ? -parts[1].length : undefined);
      for (const value of values) bases.push(path.resolve(options.baseUrl || source, value.replace('*', wildcard)));
    }
  }
  for (const base of bases) {
    for (const suffix of ['', '.ts', '.tsx', '.js', '.jsx', '.vue.ts', '.ts/index.ts', '/index.ts', '/index.js']) {
      const candidate = normalize(base.endsWith('.vue') && suffix === '' ? base + '.ts' : base + suffix);
      if (contents.has(candidate)) return { resolvedFileName: candidate, extension: candidate.endsWith('.tsx') ? ts.Extension.Tsx : ts.Extension.Ts };
    }
  }
  return resolved;
});
const program = ts.createProgram([...contents.keys()], options, host);
const checker = program.getTypeChecker();
const records = new Map(), aliases = new Map(), modules = [], diagnostics = [], written = new Set();
const isFunction = n => (ts.isFunctionDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n) || ts.isMethodDeclaration(n) || ts.isConstructorDeclaration(n) || ts.isGetAccessor(n) || ts.isSetAccessor(n)) && n.body;
function nameFor(n, sf) {
  if (ts.isConstructorDeclaration(n)) return (n.parent.name?.getText(sf) || 'class') + '.constructor';
  if (n.name) return ((ts.isClassDeclaration(n.parent) || ts.isClassExpression(n.parent)) && n.parent.name ? n.parent.name.getText(sf) + '.' : '') + n.name.getText(sf);
  if (ts.isVariableDeclaration(n.parent) || ts.isPropertyAssignment(n.parent)) return n.parent.name.getText(sf);
  if (ts.isCallExpression(n.parent)) {
    const p = n.parent;
    if (ts.isVariableDeclaration(p.parent)) return p.parent.name.getText(sf) + ' · ' + p.expression.getText(sf).split('.').pop();
    return p.expression.getText(sf).split('.').pop() + ' · 回调';
  }
  return '回调';
}
for (const [virtual, rel] of physical) {
  const sf = program.getSourceFile(virtual);
  if (sf.parseDiagnostics.length) throw new Error(rel + ': ' + ts.flattenDiagnosticMessageText(sf.parseDiagnostics[0].messageText, '\n'));
  const original = originals.get(rel);
  const module = { file: rel, language: rel.endsWith('.vue') ? 'vue' : /\.[cm]?tsx?$/.test(rel) ? 'typescript' : 'javascript', source_hash: hash(original), text: original, doc: (ts.getLeadingCommentRanges(sf.text,0) || []).map(c => sf.text.slice(c.pos,c.end)).join('\n'), functions: [] };
  function visit(n, parent) {
    let owner = parent;
    if (isFunction(n)) {
      const start = n.getStart(sf), line = sf.getLineAndCharacterOfPosition(start).line + 1;
      const name = nameFor(n, sf);
      let documentationNode = n;
      while (documentationNode.parent && (ts.isVariableDeclaration(documentationNode.parent) || ts.isVariableDeclarationList(documentationNode.parent) || ts.isVariableStatement(documentationNode.parent))) documentationNode = documentationNode.parent;
      const comments = ts.getLeadingCommentRanges(sf.text, documentationNode.pos) || [];
      const doc = comments.map(c => sf.text.slice(c.pos, c.end)).join('\n');
      const kind = ts.isConstructorDeclaration(n) ? 'constructor' : ts.isArrowFunction(n) || ts.isFunctionExpression(n) ? 'callback' : ts.isMethodDeclaration(n) ? 'method' : 'function';
      const f = { id: uid('fn', rel + ':' + start), name, qualified: (parent ? parent.qualified + '.' : '') + name, file: rel, line, signature: n.getText(sf).slice(0, n.body.getStart(sf) - start).replace(/\s+/g, ' ').trim(), language: module.language, arity: n.parameters.length, doc, source_hash: hash(doc + '\n' + n.getText(sf)), kind, calls: [], bindings: [] };
      records.set(n, f);
      if (ts.isVariableDeclaration(n.parent)) aliases.set(n.parent, f);
      module.functions.push(f); owner = f;
    }
    ts.forEachChild(n, c => visit(c, owner));
  }
  visit(sf, null);
  module.entry = { id: uid('fn', rel + ':entry'), name: '<模块初始化>', qualified: '<模块初始化>', file: rel, line: 1, signature: rel + ' module initialization', language: module.language, source_hash: hash(original), kind: 'entry', calls: [], bindings: [] };
  module.virtual = virtual;
  modules.push(module);
}
// A type annotation describes possible receivers, not the runtime dispatch target.
function propertyTarget(n) {
  const symbol = checker.getSymbolAtLocation(n.name);
  const members = symbol?.declarations || [];
  const classMember = members.some(d => ts.isClassDeclaration(d.parent) || ts.isClassExpression(d.parent));
  if (!classMember) return { node: n.name };
  if (members.every(d => d.modifiers?.some(m => m.kind === ts.SyntaxKind.StaticKeyword || m.kind === ts.SyntaxKind.PrivateKeyword))) return { node: n.name };
  let initializer = ts.isNewExpression(n.expression) ? n.expression : null;
  if (ts.isIdentifier(n.expression)) {
    const receiver = checker.getSymbolAtLocation(n.expression);
    if (written.has(receiver)) return null;
    const declaration = receiver?.valueDeclaration;
    if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer && ts.isNewExpression(declaration.initializer)) initializer = declaration.initializer;
  }
  if (!initializer) return null;
  let cls = checker.getSymbolAtLocation(initializer.expression);
  if (cls?.flags & ts.SymbolFlags.Alias) cls = checker.getAliasedSymbol(cls);
  const targets = (cls?.declarations || []).flatMap(d => (d.members || []).filter(m => m.name?.getText() === n.name.getText() && records.has(m)));
  return targets.length === 1 ? { record: records.get(targets[0]) } : null;
}
for (const module of modules) {
  function writes(n) {
    if (ts.isBinaryExpression(n) && n.operatorToken.kind >= ts.SyntaxKind.FirstAssignment && n.operatorToken.kind <= ts.SyntaxKind.LastAssignment) written.add(checker.getSymbolAtLocation(n.left));
    if ((ts.isPrefixUnaryExpression(n) || ts.isPostfixUnaryExpression(n)) && [ts.SyntaxKind.PlusPlusToken, ts.SyntaxKind.MinusMinusToken].includes(n.operator)) written.add(checker.getSymbolAtLocation(n.operand));
    ts.forEachChild(n, writes);
  }
  writes(program.getSourceFile(module.virtual));
}
function resolve(n, seen = new Set()) {
  if (!n || seen.has(n)) return null;
  seen.add(n);
  if (ts.isPropertyAccessExpression(n)) {
    const property = propertyTarget(n);
    return property ? property.record || resolve(property.node, seen) : null;
  }
  if (records.has(n)) return records.get(n);
  let symbol = checker.getSymbolAtLocation(n);
  if (written.has(symbol)) return null;
  if (symbol?.flags & ts.SymbolFlags.Alias) { try { symbol = checker.getAliasedSymbol(symbol); } catch { return null; } }
  const candidates = [];
  for (const d of symbol?.declarations || []) {
    if (records.has(d)) candidates.push(records.get(d));
    else if (aliases.has(d)) candidates.push(aliases.get(d));
    else if (ts.isVariableDeclaration(d) || ts.isPropertyAssignment(d)) {
      if (d.initializer && (ts.isIdentifier(d.initializer) || ts.isPropertyAccessExpression(d.initializer))) {
        const r = resolve(d.initializer, seen);
        if (r) candidates.push(r);
      }
    } else if (ts.isShorthandPropertyAssignment(d)) {
      const value = checker.getShorthandAssignmentValueSymbol(d);
      for (const dec of value?.declarations || []) if (records.has(dec) || aliases.has(dec)) candidates.push(records.get(dec) || aliases.get(dec));
    } else if (ts.isClassDeclaration(d)) {
      const ctor = d.members.find(ts.isConstructorDeclaration);
      if (records.has(ctor)) candidates.push(records.get(ctor));
    }
  }
  const unique = [...new Map(candidates.map(c => [c.id, c])).values()];
  return unique.length === 1 ? unique[0] : null;
}
for (const module of modules) {
  const sf = program.getSourceFile(module.virtual);
  function visit(n, owner) {
    owner = records.get(n) || owner;
    if (ts.isCallExpression(n) || ts.isNewExpression(n)) {
      const target = resolve(n.expression);
      if (target) owner.calls.push({ target: target.id });
      else diagnostics.push({ file: module.file, line: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1, function: owner.id, expression: n.expression.getText(sf), reason: 'external_or_dynamic' });
      for (const arg of n.arguments || []) {
        const target = resolve(arg);
        if (target) owner.bindings.push({ target: target.id });
      }
    }
    ts.forEachChild(n, c => visit(c, owner));
  }
  visit(sf, module.entry);
  if (module.entry.calls.length || module.entry.bindings.length || diagnostics.some(d => d.function === module.entry.id)) module.functions.unshift(module.entry);
  delete module.entry; delete module.virtual;
}
process.stdout.write(JSON.stringify({ modules, diagnostics }));
