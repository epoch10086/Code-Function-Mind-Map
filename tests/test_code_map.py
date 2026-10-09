"""Observable parser, graph, update and recovery contract tests."""
from pathlib import Path
import hashlib
import json
import zipfile
import shutil
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/code-function-mind-map/scripts'))
from analyzer import analyze, doctor
from code_map import build, install_snapshot, output_lock
from model import load, write, Module, Function, assemble, uid
from render import Workbook, enrich
from validation import validate_output


def calls(graph):
    names={n['id']:n['qualified'] for n in graph['nodes'] if n['type']=='function'}
    return {(names[e['from']],names[e['to']]) for e in graph['edges'] if e['type']!='tree'}


class Parsers(unittest.TestCase):
    def scan(self,language):
        source=ROOT/'tests/fixtures'/language
        return analyze(source,ROOT/'.artifacts'/language,{'exclude':[]})

    def test_python_imports_methods_recursion_callbacks(self):
        g=self.scan('python');pairs=calls(g)
        self.assertIn(('main','Worker.__init__'),pairs)
        self.assertIn(('main','Worker.run'),pairs)
        self.assertIn(('callback','helper'),pairs)
        self.assertIn(('recurse','recurse'),pairs)
        names={n['id']:n['qualified'] for n in g['nodes'] if n['type']=='function'}
        self.assertIn(('main','callback'),{(names[e['from']],names[e['to']]) for e in g['bindings']})
        self.assertNotIn(('main','callback'),pairs)
        self.assertNotIn(('consumer','helper'),pairs)
        self.assertTrue(any(d['expression']=='register' for d in g['diagnostics']))

    def test_web_vue_react_aliases(self):
        pairs=calls(self.scan('web'))
        for a,b in [('main','helper'),('main','leaf'),('main','Worker.constructor'),('main','Worker.run'),('submit','helper'),('View','leaf'),('TypedView','helper'),('recurse','recurse')]:
            self.assertIn((a,b),pairs)

    def test_java_constructors_overload_ambiguity(self):
        g=self.scan('java');pairs=calls(g)
        for a,b in [('Main.main','Worker.Worker'),('Main.main','Worker.run'),('Main.main','Util.help'),('Worker.run','Util.help')]:
            self.assertIn((a,b),pairs)
        self.assertFalse(any(b=='Util.overloaded' for a,b in pairs))
        self.assertNotIn(('Dynamic.consume','Worker.run'),pairs)
        self.assertTrue(any(d['reason']=='ambiguous' for d in g['diagnostics']))

    def test_c_header_linkage_and_macro_diagnostic(self):
        g=self.scan('c')
        self.assertIn(('main','helper'),calls(g))
        self.assertTrue(any(d['expression']=='UNKNOWN' for d in g['diagnostics']))

    def test_cpp_namespace_and_receiver(self):
        pairs=calls(self.scan('cpp'))
        self.assertIn(('main','util.Worker.run'),pairs)
        self.assertIn(('main','util.help'),pairs)
        self.assertIn(('util.Worker.run','util.help'),pairs)

    def test_go_package_and_receiver(self):
        pairs=calls(self.scan('go'))
        self.assertIn(('main','Worker.Run'),pairs)
        self.assertIn(('Worker.Run','Help'),pairs)
        self.assertIn(('main','Help'),pairs)

    def test_same_names_not_globally_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'a.py').write_text('def helper(): return 1\ndef main(): return missing()\n')
            (p/'b.py').write_text('def missing(): return 2\n')
            g=analyze(p,p/'out',{})
            self.assertNotIn(('main','missing'),calls(g))


class Updates(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.source=Path(self.temp.name)/'项目 space'
        self.source.mkdir()
        self.code=self.source/'main.py'
        self.code.write_text('def helper(): return 1\ndef main(): return helper()\n',encoding='utf-8')
        self.output=self.source/'docs/code-map'

    def tearDown(self):
        self.temp.cleanup()

    def test_repeat_new_changed_deleted_source_and_notes(self):
        original=self.code.read_bytes()
        build(self.source,self.output)
        g=load(self.output/'auxiliary/data/graph.json')
        f=next(n for n in g['nodes'] if n['type']=='function' and n['name']=='helper')
        write(self.output/'annotations.json',{'files':{},'functions':{f['id']:{'source_hash':f['source_hash'],'purpose':'返回测试值'}}})
        build(self.source,self.output)
        self.assertEqual(original,self.code.read_bytes())
        self.assertIn('双击', (self.output/'README.md').read_text(encoding='utf-8'))
        (self.source/'new.py').write_text('def added(): return 2\n')
        self.code.write_text('def helper(): return 3\ndef main(): return helper()\n')
        build(self.source,self.output)
        g=load(self.output/'auxiliary/data/graph.json')
        updated=next(n for n in g['nodes'] if n['type']=='function' and n['name']=='helper')
        self.assertEqual(updated['purpose_status'],'needs_refresh')
        (self.source/'new.py').unlink()
        build(self.source,self.output)
        self.assertEqual(validate_output(self.output)['files'],1)
        self.assertTrue((self.output/'history').is_dir())

    def test_syntax_failure_preserves_snapshot(self):
        build(self.source,self.output)
        before=(self.output/'code-function-call-mindmap.xmind').read_bytes()
        self.code.write_text('def broken(:\n')
        with self.assertRaises(SyntaxError):build(self.source,self.output)
        self.assertEqual(before,(self.output/'code-function-call-mindmap.xmind').read_bytes())
        self.assertFalse((self.output/'.code-map.lock').exists())

    def test_lock_blocks_concurrent_generation(self):
        self.output.mkdir(parents=True)
        with output_lock(self.output):
            with self.assertRaises(FileExistsError):build(self.source,self.output)

    def test_bootstrap_waits_and_propagates_failure(self):
        build(self.source,self.output)
        success=subprocess.run([sys.executable,str(self.output/'auxiliary/update.py')],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(success.returncode,0,success.stderr)
        self.assertIn('main_file',success.stdout)
        before=(self.output/'code-function-call-mindmap.xmind').read_bytes()
        self.code.write_text('def broken(:\n')
        failure=subprocess.run([sys.executable,str(self.output/'auxiliary/update.py')],capture_output=True,text=True,encoding='utf-8')
        self.assertNotEqual(failure.returncode,0)
        self.assertEqual(before,(self.output/'code-function-call-mindmap.xmind').read_bytes())
        if sys.platform=='win32':
            launcher=subprocess.run(['cmd.exe','/d','/c',str(self.output/'update_mindmap.cmd'),'--no-pause'],capture_output=True,text=True,encoding='utf-8',errors='replace')
            self.assertNotEqual(launcher.returncode,0)
            self.assertIn('[FAILED]',launcher.stdout)
            self.assertNotIn('[DONE]',launcher.stdout)
            self.assertEqual(before,(self.output/'code-function-call-mindmap.xmind').read_bytes())

    def test_missing_parser_is_explicit(self):
        with patch('analyzer.shutil.which',return_value=None):
            result=doctor(ROOT/'tests/fixtures/web',self.output,[])
        self.assertFalse(result['ready'])

    def test_all_languages_render_and_validate(self):
        for language in ('python','web','java','c','cpp','go'):
            with self.subTest(language=language):
                output=self.source/('output-'+language)
                report=build(ROOT/'tests/fixtures'/language,output)
                self.assertGreater(report['functions'],0)
                self.assertEqual(report['structure'],'passed')

    def test_user_files_preserved_and_unowned_file_rejected(self):
        build(self.source,self.output)
        user=self.output/'notes.txt';user.write_text('keep')
        build(self.source,self.output)
        self.assertEqual(user.read_text(),'keep')
        other=self.source/'other';other.mkdir()
        (other/'README.md').write_text('user documentation')
        with self.assertRaises(ValueError):build(self.source,other)
        self.assertEqual((other/'README.md').read_text(),'user documentation')

    def test_failed_install_rolls_back_every_file(self):
        build(self.source,self.output)
        manifest=load(self.output/'.generated-files.json')['files']
        before={name:(self.output/name).read_bytes() for name in manifest}
        staging=self.source/'stage';staging.mkdir()
        for name in manifest:
            p=staging/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'changed')
        import code_map
        original=code_map.os.replace
        count=0
        def fail_second(a,b):
            nonlocal count
            count+=1
            if count==2:raise PermissionError('injected locked file')
            return original(a,b)
        with patch('code_map.os.replace',side_effect=fail_second):
            with self.assertRaises(PermissionError):install_snapshot(staging,self.output,manifest)
        self.assertEqual(before,{name:(self.output/name).read_bytes() for name in manifest})

    def test_large_graph_and_fanout_pagination(self):
        text='\n'.join(f'def f{i}(): return {i}' for i in range(90))
        text+='\ndef main():\n'+''.join(f'    f{i}()\n' for i in range(90))
        self.code.write_text(text)
        # All callees become visible via per-file selection only if their degree is high.
        for i in range(5):text+=f'\ndef caller{i}():\n'+''.join(f'    f{j}()\n' for j in range(90))
        self.code.write_text(text)
        report=build(self.source,self.output)
        self.assertGreater(report['sheets'],2)
        self.assertEqual(report['canonical_relationships'],540)
        self.assertEqual(report['visible_relationships']+report['target_references'],540)


class EvidenceRegression(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.source=Path(self.temp.name)/'回归 space'
        self.source.mkdir()
        self.output=self.source/'docs/code-map'

    def tearDown(self):
        self.temp.cleanup()

    def project(self, files):
        for name,text in files.items():
            p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(text,encoding='utf-8')
        return analyze(self.source,self.output,{})

    def test_python_scope_reassignment_and_dynamic_dispatch(self):
        g=self.project({'a.py':'def a_helper(): pass\n','b.py':'def b_helper(): pass\n','main.py':'''from a import a_helper as helper
def local():
    from b import b_helper as helper
    helper()
def main(other):
    helper()
    w = Worker()
    w.run()
    w = other
    w.run()
def global_helper(): pass
class Worker:
    def run(self): pass
    def dispatch(self): self.run()
    def global_helper(self): pass
    def bare(self): global_helper()
class Child(Worker):
    def run(self): pass
'''})
        pairs=calls(g)
        self.assertIn(('main','a_helper'),pairs)
        self.assertIn(('local','b_helper'),pairs)
        self.assertIn(('main','Worker.run'),pairs)
        self.assertIn(('Worker.bare','global_helper'),pairs)
        self.assertNotIn(('Worker.bare','Worker.global_helper'),pairs)
        self.assertNotIn(('Worker.dispatch','Worker.run'),pairs)
        self.assertTrue(any(d['line']==10 and d['expression']=='w.run' for d in g['diagnostics']))
        self.assertTrue(any(d['expression']=='self.run' for d in g['diagnostics']))

    def test_python_lambda_registration_is_separate(self):
        g=self.project({'main.py':'def leaf(): pass\ndef main():\n    cb = lambda: leaf()\n    register(cb)\n    cb()\n'})
        names={n['id']:n['qualified'] for n in g['nodes'] if n['type']=='function'}
        callback=next(name for name in names.values() if '<lambda' in name)
        self.assertIn((callback,'leaf'),calls(g))
        self.assertIn(('main',callback),calls(g))
        self.assertIn(('main',callback),{(names[e['from']],names[e['to']]) for e in g['bindings']})

    def test_python_binding_targets_invalidate_receiver(self):
        g=self.project({'main.py':'''class Worker:
 def run(self): pass
def loop(items):
 w = Worker()
 for w in items: w.run()
def context(cm):
 w = Worker()
 with cm as w: w.run()
def comprehension(items):
 w = Worker()
 return [w.run() for w in items]
def caught():
 w = Worker()
 try: fail()
 except Exception as w: w.run()
'''})
        for owner in ('loop','context','comprehension','caught'):
            self.assertNotIn((owner,'Worker.run'),calls(g))
        self.assertEqual(sum(d['expression']=='w.run' for d in g['diagnostics']),4)

    def test_java_constructed_subtype_and_reassignment(self):
        g=self.project({'Main.java':'''class Base { void run() {} }
class Sub extends Base { void run() {} }
class Main {
 static void main(Base other) {
  Base x = new Sub();
  x.run();
  x = other;
  x.run();
 }
 void dispatch(Base x) { x.run(); }
}'''})
        self.assertIn(('Main.main','Sub.run'),calls(g))
        self.assertNotIn(('Main.main','Base.run'),calls(g))
        self.assertNotIn(('Main.dispatch','Base.run'),calls(g))
        self.assertTrue(any(d['line']==8 and d['expression']=='x.run' for d in g['diagnostics']))

    def test_native_anonymous_callbacks(self):
        fixtures={
            'java':('Main.java','class Main { static void leaf() {} static void main() { register(() -> leaf()); } }'),
            'cpp':('main.cpp','void leaf() {} int main() { auto cb = [](){ leaf(); }; register_cb(cb); cb(); }'),
            'go':('main.go','package main\nfunc leaf() {}\nfunc main(){cb:=func(){leaf()}; register(cb); cb()}'),
        }
        for language,(filename,text) in fixtures.items():
            with self.subTest(language=language):
                directory=self.source/language;directory.mkdir()
                (directory/filename).write_text(text,encoding='utf-8')
                g=analyze(directory,self.output,{})
                names={n['id']:n['qualified'] for n in g['nodes'] if n['type']=='function'}
                callback=next(name for name in names.values() if '<callback' in name)
                leaf='Main.leaf' if language=='java' else 'leaf'
                main='Main.main' if language=='java' else 'main'
                self.assertIn((callback,leaf),calls(g))
                self.assertIn((main,callback),{(names[e['from']],names[e['to']]) for e in g['bindings']})
                if language!='java':self.assertIn((main,callback),calls(g))

    def test_java_anonymous_subclass_remains_diagnostic(self):
        g=self.project({'Main.java':'class Base { void run() {} } class Main { static void main() { Base x = new Base() { void run() {} }; x.run(); } }'})
        self.assertNotIn(('Main.main','Base.run'),calls(g))
        self.assertTrue(any(d['expression']=='x.run' for d in g['diagnostics']))

    def test_reciprocal_curves_use_separate_lanes(self):
        self.project({'main.py':'def a():\n b(); start(); stop()\ndef b(): a()\ndef start(): pass\ndef stop(): pass\n'})
        report=build(self.source,self.output)
        self.assertGreaterEqual(report['visible_relationships'],2)
        # Independent validation checks endpoint bodies and both path directions.
        self.assertEqual(validate_output(self.output)['structure'],'passed')

    def test_competing_reciprocal_paths_fallback_to_references(self):
        functions=[Function(uid('fn','probe:'+str(i)),'start_'+str(i),'start_'+str(i),'main.py',i+1,'def start_'+str(i)+'()', 'python') for i in range(5)]
        pairs=[(1,3),(1,0),(4,3),(2,3),(2,0),(0,2),(2,4),(3,4),(3,1)]
        graph=assemble([Module('main.py','python','hash','',functions=functions)],{(functions[a].id,functions[b].id) for a,b in pairs},set(),[],self.source)
        enrich(graph,{})
        workbook=Workbook(graph,{'font_size':17,'lane_gap':32}).build()
        for name,data in workbook.artifacts().items():
            target=self.output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        write(self.output/'auxiliary/data/graph.json',graph)
        report=validate_output(self.output)
        self.assertEqual(report['visible_relationships']+report['target_references'],9)

    def test_native_recursion_callbacks_and_overload_scope(self):
        fixtures={
            'c':{'main.c':'void callback() {} void register_callback(void (*fn)(void)); int recurse(int n) { return n ? recurse(n-1) : 0; } int main() { register_callback(callback); return recurse(1); }'},
            'cpp':{'main.cpp':'void callback() {} void register_callback(void (*fn)()); int recurse(int n) { return n ? recurse(n-1) : 0; } int overloaded(int x) { return x; } int overloaded(const char* x) { return 0; } int main() { register_callback(callback); overloaded(1); return recurse(1); }'},
            'go':{'main.go':'package main\nfunc callback() {}\nfunc recurse(n int) int { if n > 0 { return recurse(n-1) }; return 0 }\nfunc main() { register(callback); recurse(1) }'},
            'java':{'Main.java':'class Main { static void callback() {} static int recurse(int n) { return n > 0 ? recurse(n-1) : 0; } static void main() { register(Main::callback); recurse(1); } }'},
        }
        for language,files in fixtures.items():
            with self.subTest(language=language):
                directory=self.source/language;directory.mkdir()
                for name,text in files.items():(directory/name).write_text(text,encoding='utf-8')
                g=analyze(directory,self.output,{})
                names={n['id']:n['qualified'] for n in g['nodes'] if n['type']=='function'}
                prefix='Main.' if language=='java' else ''
                self.assertIn((prefix+'recurse',prefix+'recurse'),calls(g))
                self.assertIn((prefix+'main',prefix+'callback'),{(names[e['from']],names[e['to']]) for e in g['bindings']})
                self.assertNotIn((prefix+'main',prefix+'callback'),calls(g))
                if language=='cpp':
                    self.assertNotIn(('main','overloaded'),calls(g))
                    self.assertTrue(any(d['reason']=='ambiguous' for d in g['diagnostics']))

    def test_typescript_dynamic_receiver_and_wrapper_result(self):
        g=self.project({'main.ts':'''class Base { run() {} }
class Sub extends Base { run() {} }
function dispatch(x: Base) { x.run(); }
function original() {}
function replacement() {}
function wrap(cb: () => void) { return replacement; }
const transformed = wrap(original);
function main() { transformed(); const x: Base = new Sub(); x.run(); }
'''})
        pairs=calls(g)
        self.assertNotIn(('dispatch','Base.run'),pairs)
        self.assertNotIn(('main','original'),pairs)
        self.assertIn(('main','Sub.run'),pairs)
        self.assertTrue(any(d['expression']=='transformed' for d in g['diagnostics']))
        names={n['id']:n['qualified'] for n in g['nodes'] if n['type']=='function'}
        self.assertTrue(any(names[e['to']]=='original' for e in g['bindings']))

    def test_doc_only_changes_invalidate_javascript_and_java_annotations(self):
        for filename,first,second in [('main.ts','/** old */\nfunction main() {}','/** new */\nfunction main() {}'),('Main.java','class Main {\n /** old */\n static void main() {}\n}','class Main {\n /** new */\n static void main() {}\n}')]:
            with self.subTest(filename=filename):
                g=self.project({filename:first})
                f=next(n for n in g['nodes'] if n['type']=='function' and n['file']==filename)
                self.project({filename:second})
                changed=analyze(self.source,self.output,{})
                enrich(changed,{'functions':{f['id']:{'source_hash':f['source_hash'],'purpose':'旧解释'}}})
                updated=next(n for n in changed['nodes'] if n['id']==f['id'])
                self.assertNotEqual(updated['source_hash'],f['source_hash'])
                self.assertNotEqual(updated['purpose_status'],'annotation')
                self.assertEqual(updated['purpose_status'],'needs_refresh')
                self.assertNotEqual(updated['purpose'],'旧解释')

    def test_tampered_target_links_are_rejected(self):
        self.project({'a/main.py':'from b.worker import leaf\ndef main(): leaf()\n','b/worker.py':'def leaf(): pass\n'})
        build(self.source,self.output)
        xmind=self.output/'code-function-call-mindmap.xmind'
        with zipfile.ZipFile(xmind) as z:
            payload={name:z.read(name) for name in z.namelist()}
        sheets=json.loads(payload['content.json'])
        nav=load(self.output/'auxiliary/data/navigation-index.json')
        changed=0
        for sheet in sheets:
            for topic in sheet['rootTopic']['children']['detached']:
                if nav['topic_roles'][topic['id']]=='target_reference':
                    topic['href']='xmind:#'+sheets[0]['rootTopic']['id'];changed+=1
        self.assertGreater(changed,0)
        payload['content.json']=json.dumps(sheets).encode()
        with zipfile.ZipFile(xmind,'w') as z:
            for name,data in payload.items():z.writestr(name,data)
        with self.assertRaisesRegex(ValueError,'target function'):validate_output(self.output)


if __name__=='__main__':unittest.main()
