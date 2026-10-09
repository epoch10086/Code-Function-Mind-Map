"""Bounded, paginated XMind view; canonical data is never filtered."""
from collections import defaultdict
from pathlib import Path
import io
import json
import math
import zipfile
import html
import fnmatch
import re
from model import uid


def character_width(character):
    return 2 if ord(character)>255 or character in 'MWmw@%' else 1


def compact(text, limit=23, middle=False):
    text=str(text).replace('\n',' ')
    if sum(map(character_width,text))<=limit:
        return text
    budget=max(0,limit-2)  # Include the ellipsis in the width budget.
    prefix_budget=max(1,budget//3) if middle else budget
    prefix=''
    for character in text:
        if sum(map(character_width,prefix))+character_width(character)>prefix_budget:
            break
        prefix+=character
    suffix=''
    if middle:
        suffix_budget=budget-sum(map(character_width,prefix))
        for character in reversed(text[len(prefix):]):
            if sum(map(character_width,suffix))+character_width(character)>suffix_budget:
                break
            suffix=character+suffix
    return prefix+'…'+suffix


def entry_function(function):
    name = function['name'].split(' · ')[0].rsplit('.',1)[-1]
    words = re.sub(r'([a-z])([A-Z])',r'\1_\2',name).lower().strip('_').split('_')
    return function['kind'] in {'entry','constructor'} or name in {'api_request','configure_api_client','beforeEach','afterEach'} or bool(set(words)&{'main','init','initialize','bootstrap','setup','start','stop','login','logout','signin','signout'})


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def enrich(graph, annotations):
    modules = {n['file']: n for n in graph['nodes'] if n['type'] == 'reference'}
    for n in graph['nodes']:
        if n['type'] not in {'reference', 'function'}:
            continue
        section = 'files' if n['type'] == 'reference' else 'functions'
        key = n['file'] if section == 'files' else n['id']
        annotation = annotations.get(section, {}).get(key, {})
        valid = bool(annotation) and annotation.get('source_hash') == n.get('source_hash')
        n['purpose_status'] = 'annotation' if valid else 'needs_refresh' if annotation else 'source_doc' if n.get('doc') else 'needs_description'
        n['purpose'] = annotation.get('purpose', '') if valid else n.get('doc', '') or '用途待补充：请按源码确认职责'
        n['details'] = annotation.get('details', '') if valid else ''
        if section == 'functions':
            n['file_purpose'] = modules[n['file']]['purpose']


def group_for(file, config):
    for rule in config.get('groups', []):
        if fnmatch.fnmatch(file, rule['pattern']):
            return rule['title']
    parent = Path(file).parent.as_posix()
    if parent == '.':
        return '入口与根目录'
    if parent.startswith('src/'):
        parent = parent[4:]
    return parent


def point(points, t):
    weights = ((1-t)**3, 3*(1-t)**2*t, 3*(1-t)*t*t, t**3)
    return tuple(sum(w*p[i] for w,p in zip(weights, points)) for i in (0,1))


def curve_geometry(rel, geometry):
    a, b = geometry[rel['end1Id']], geometry[rel['end2Id']]
    return [(a['x'] + rel['lineEndPoints']['0']['x'], a['y'] + rel['lineEndPoints']['0']['y']), (a['x'] + rel['controlPoints']['0']['x'], a['y'] + rel['controlPoints']['0']['y']), (b['x'] + rel['controlPoints']['1']['x'], b['y'] + rel['controlPoints']['1']['y']), (b['x'] + rel['lineEndPoints']['1']['x'], b['y'] + rel['lineEndPoints']['1']['y'])]


def hits(points, boxes, exclude):
    for index in range(1, 200):
        x,y = point(points, index/200)
        for tid, box in boxes.items():
            if tid not in exclude and abs(x-box['x']) < box['width']/2+8 and abs(y-box['y']) < box['height']/2+8:
                return True
    return False


def crosses_endpoint(points, boxes, endpoints):
    for index in range(1,200):
        x,y=point(points,index/200)
        for tid in endpoints:
            box=boxes[tid]
            if abs(x-box['x'])<box['width']/2-2 and abs(y-box['y'])<box['height']/2-2:
                return True
    return False


class Workbook:
    def __init__(self, graph, config):
        self.graph, self.config = graph, config
        self.functions = {n['id']: n for n in graph['nodes'] if n['type'] == 'function'}
        self.calls = defaultdict(list)
        self.incoming = defaultdict(list)
        for e in graph['edges']:
            if e['type'] != 'tree':
                self.calls[e['from']].append(e['to'])
                self.incoming[e['to']].append(e['from'])
        self.visible = set()
        by_file = defaultdict(list)
        for f in self.functions.values():
            by_file[f['file']].append(f)
            if f['incoming'] + f['outgoing'] >= 5 or entry_function(f):
                self.visible.add(f['id'])
        for functions in by_file.values():
            best = sorted(functions, key=lambda n: (-n['incoming']-n['outgoing'], -n['outgoing'], n['line'], n['name']))[:2]
            self.visible.update(n['id'] for n in best)
        self.sheets, self.geometry, self.roles, self.locations = [], {}, {}, {}
        self.relations, self.references = {}, {}
        self.home = uid('topic', 'home:root')

    def topic(self, key, title, x, y, role='function', width=300, height=82, href=None, note='', color='#e0edf5', font=None):
        tid = uid('topic', key)
        font = font or self.config.get('font_size',17)
        self.geometry[tid] = dict(x=x,y=y,width=width,height=height)
        self.roles[tid] = role
        data = {'id':tid,'class':'topic','title':title,'position':{'x':x,'y':y},'customWidth':width,'notes':{'plain':{'content':note}},'style':{'id':uid('style',tid),'properties':{'shape-class':'org.xmind.topicShape.roundedRect','fo:font-family':'Microsoft YaHei','fo:font-size':f'{font}pt','fo:color':'#173047','svg:fill':color,'fo:text-align':'center'}}}
        if href:
            data['href'] = 'xmind:#' + href
        return data

    def sheet(self, key, title, back=True):
        root = self.topic(key+':root',compact(title,48),0,0,role='root',width=700,height=92,font=20)
        if key == 'home':
            root['id'] = self.home
        root['children'] = {'detached':[]}
        sheet = {'id':uid('sheet',key),'class':'sheet','title':title,'rootTopic':root,'topicPositioning':'free','floatingTopicFlexibility':'flexible','relationships':[]}
        self.sheets.append(sheet)
        if back:
            self.add(sheet,self.topic(key+':back','返回目录',-650,0,role='navigation',width=180,height=58,href=self.home,font=16))
        return sheet

    @staticmethod
    def topics(sheet):
        return [sheet['rootTopic'],*sheet['rootTopic']['children']['detached']]

    @staticmethod
    def add(sheet, topic):
        sheet['rootTopic']['children']['detached'].append(topic)

    def note(self, f):
        targets = [self.functions[k] for k in self.calls[f['id']]]
        callers = [self.functions[k] for k in self.incoming[f['id']]]
        bindings = [self.functions[e['to']] for e in self.graph['bindings'] if e['from']==f['id']]
        line = lambda t: f"{t['file']}:{t['line']} · {t['qualified']}"
        return '\n'.join([f"完整名称：{f['qualified']}",f"源码：{self.graph['meta']['source']}/{f['file']}:{f['line']}",f"签名：{f['signature']}",f"用途：{f['purpose']}",f"说明状态：{f['purpose_status']}",f"文件职责：{f['file_purpose']}",f"入度 {f['incoming']} · 出度 {f['outgoing']}",f.get('details',''),'返回/异常/复杂度：以源码及类型为准，未文档化的行为未推断。','调用者：\n'+'\n'.join(map(line,callers)),'直接调用：\n'+'\n'.join(map(line,targets)),'回调注册/传参（非直接调用）：\n'+'\n'.join(map(line,bindings)),'限制：仅静态可确认调用；动态调用及外部依赖见诊断清单。'])

    def build(self):
        groups = defaultdict(list)
        for k in sorted(self.visible,key=lambda k:(self.functions[k]['file'],self.functions[k]['line'],k)):
            groups[group_for(self.functions[k]['file'],self.config)].append(k)
        for m in self.graph['files']:
            groups[group_for(m['file'],self.config)]
        pages = []
        for group, keys in sorted(groups.items()):
            chunks, batch, edges, cells = [], [], 0, 0
            for key in keys:
                targets = [t for t in self.calls[key] if t in self.visible]
                portions = [targets[i:i+30] for i in range(0,len(targets),30)] or [[]]
                for targets in portions:
                    cost = 1+len(targets)
                    if batch and (len(batch)>=24 or edges+len(targets)>40 or cells+cost>32):
                        chunks.append(batch); batch=[]; edges=0; cells=0
                    batch.append((key,targets)); edges+=len(targets); cells+=cost
            if batch:
                chunks.append(batch)
            summaries = [n for n in self.graph['nodes'] if n['type']=='reference' and group_for(n['file'],self.config)==group and not any(f['file']==n['file'] for f in self.functions.values())]
            for i in range(0,len(summaries),24):
                chunks.append([('file:'+n['id'],[]) for n in summaries[i:i+24]])
            if not chunks:
                chunks=[[]]
            for index,batch in enumerate(chunks):
                sheet=self.sheet(group+':'+str(index),group+(f' · {index+1}/{len(chunks)}' if len(chunks)>1 else ''))
                pages.append((sheet,batch))
                for key,targets in batch:
                    if not key.startswith('file:') and key not in self.locations:
                        self.locations[key]={'topic_id':uid('topic',sheet['id']+':'+key),'sheet_id':sheet['id']}
        directory=self.sheet('home',self.graph['meta']['title'],back=False)
        self.sheets.remove(directory); self.sheets.insert(0,directory)
        self.add(directory,self.topic('help','目录 → 模块页 → 目标函数\n完整数据见 JSON / Markdown',0,150,role='legend',width=700,height=82,font=17,color='#fff0cc'))
        for index,(sheet,batch) in enumerate(pages):
            title=compact(sheet['title'])+f'\n重点函数 {sum(not k.startswith("file:") for k,t in batch)}'
            self.add(directory,self.topic('link:'+sheet['id'],title,(-630,-210,210,630)[index%4],320+(index//4)*132,role='navigation',height=90,href=sheet['rootTopic']['id'],font=17))
        modules={n['id']:n for n in self.graph['nodes'] if n['type']=='reference'}
        for sheet,batch in pages:
            cells=0; caller_topics={}; reserved=[]
            for key,targets in batch:
                x=(-630,-210,210,630)[cells%4]; y=210+(cells//4)*124; cells+=1
                if key.startswith('file:'):
                    m=modules[key[5:]]
                    node=self.topic(sheet['id']+':'+key,compact(Path(m['file']).name)+'\n'+compact(m['purpose']),x,y,role='file_summary',font=16,color='#ededed',note=m['file']+'\n'+m['purpose'])
                    self.add(sheet,node); continue
                f=self.functions[key]
                primary=self.locations[key]['sheet_id']==sheet['id']
                display_name='初始化' if f['kind']=='entry' else f['name'].removesuffix(' · 回调')
                first_line=compact(Path(f['file']).name,6)+' · '+compact(display_name,12,middle=True)
                title=first_line+f"\n入度 {f['incoming']} · 出度 {f['outgoing']}"
                caller=self.topic(sheet['id']+':'+key,title,x,y,role='function' if primary else 'caller_reference',href=None if primary else self.locations[key]['topic_id'],note=self.note(f),color='#fff0cc' if f['incoming']+f['outgoing']>=5 else '#e0edf5')
                self.add(sheet,caller);caller_topics[key]=caller
                for target in targets:
                    tx=(-630,-210,210,630)[cells%4]; ty=210+(cells//4)*124;cells+=1
                    reserved.append((key,target,caller,tx,ty))
            arrivals=defaultdict(int); departures=defaultdict(int)
            for key,target,caller,x,y in reserved:
                t=self.functions[target]
                reference=self.topic(sheet['id']+':ref:'+key+'>'+target,compact(self.functions[key]['name'],21,middle=True)+' →\n'+compact(t['name'],23,middle=True),x,y,role='target_reference',href=self.locations[target]['topic_id'],note=f"调用者：{self.functions[key]['file']}:{self.functions[key]['line']} · {self.functions[key]['name']}\n目标：{t['file']}:{t['line']} · {t['qualified']}",font=16,color='#e5efdf')
                target_topic=caller_topics.get(target)
                rel=None
                if target_topic and key!=target:
                    a,b=self.geometry[caller['id']],self.geometry[target_topic['id']]
                    vertical=abs(b['x']-a['x'])<300
                    direction=1 if b['x']>=a['x'] else -1
                    target_direction=direction if vertical else -direction
                    order=1 if (b['y']>a['y'] if vertical else b['x']>a['x']) else -1
                    offset_a=order*(departures[key]*self.config.get('lane_gap',32)-16)
                    offset_b=order*(arrivals[target]*self.config.get('lane_gap',32)-16)
                    if max(abs(offset_a),abs(offset_b))<=32 and math.dist((a['x'],a['y']),(b['x'],b['y']))<=700:
                        rid=uid('rel',sheet['id']+key+target)
                        rel={'id':rid,'class':'relationship','end1Id':caller['id'],'end2Id':target_topic['id'],'title':'','lineEndPoints':{'0':{'x':direction*150,'y':offset_a},'1':{'x':target_direction*150,'y':offset_b}},'controlPoints':{'0':{'x':direction*230,'y':offset_a},'1':{'x':target_direction*230,'y':offset_b}},'style':{'id':uid('style',rid),'properties':{'shape-class':'org.xmind.relationshipShape.curved','arrow-begin-class':'org.xmind.arrowShape.none','arrow-end-class':'org.xmind.arrowShape.triangle','line-color':'#376f7b','line-width':'1pt'}}}
                        points=curve_geometry(rel,self.geometry)
                        boxes={node['id']:self.geometry[node['id']] for node in self.topics(sheet)}
                        boxes.update({f'reserved-{i}':dict(x=rx,y=ry,width=300,height=82) for i,(_,_,_,rx,ry) in enumerate(reserved)})
                        if hits(points,boxes,{caller['id'],target_topic['id']}) or crosses_endpoint(points,boxes,{caller['id'],target_topic['id']}):
                            rel=None
                        existing=[curve_geometry(line,self.geometry) for line in sheet['relationships']]
                        if points in existing or list(reversed(points)) in existing:
                            rel=None
                if rel:
                    sheet['relationships'].append(rel);self.relations[rel['id']]=[key,target]
                    departures[key]+=1;arrivals[target]+=1
                    self.geometry.pop(reference['id']);self.roles.pop(reference['id'])
                else:
                    self.add(sheet,reference);self.references[reference['id']]=[key,target]
        return self

    def artifacts(self):
        result={}
        archive=io.BytesIO()
        payload={'content.json':self.sheets,'metadata.json':{'creator':{'name':'Code Function Mind Map','version':'1'},'activeSheetId':self.sheets[0]['id']},'manifest.json':{'file-entries':{'content.json':{},'metadata.json':{}}}}
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name,value in payload.items():
                z.writestr(name,json_bytes(value))
        result['code-function-call-mindmap.xmind']=archive.getvalue()
        navigation={'functions':{k:{'visible':k in self.visible,**self.locations.get(k,{})} for k in self.functions},'visible_functions':sorted(self.visible),'hidden_functions':sorted(set(self.functions)-self.visible),'relationship_source':self.relations,'reference_source':self.references,'geometry':self.geometry,'topic_roles':self.roles,'sheets': [{'id':s['id'],'title':s['title']} for s in self.sheets]}
        navigation['visible_relationships']=len(self.relations)+len(self.references)
        navigation['canonical_relationships']=sum(e['type']!='tree' for e in self.graph['edges'])
        result['auxiliary/data/navigation-index.json']=json_bytes(navigation)
        for sheet in self.sheets:
            nodes=[]
            for t in self.topics(sheet):
                r=self.geometry[t['id']]
                nodes.append({'id':t['id'],'type':'text','text':t['title'],'x':r['x']-r['width']/2,'y':r['y']-r['height']/2,'width':r['width'],'height':r['height'],'color':t['style']['properties']['svg:fill']})
            edges=[{'id':r['id'],'fromNode':r['end1Id'],'toNode':r['end2Id'],'fromSide':'right' if r['lineEndPoints']['0']['x']>0 else 'left','toSide':'right' if r['lineEndPoints']['1']['x']>0 else 'left','toEnd':'arrow'} for r in sheet['relationships']]
            result['auxiliary/canvas/'+sheet['id']+'.canvas']=json_bytes({'nodes':nodes,'edges':edges})
            result['auxiliary/previews/'+sheet['id']+'.svg']=self.svg(sheet).encode('utf-8')
        return result

    def svg(self,sheet):
        boxes=[self.geometry[t['id']] for t in self.topics(sheet)]
        left=min(b['x']-b['width']/2 for b in boxes)-30;top=min(b['y']-b['height']/2 for b in boxes)-30
        width=max(b['x']+b['width']/2 for b in boxes)-left+30;height=max(b['y']+b['height']/2 for b in boxes)-top+30
        lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{left} {top} {width} {height}">','<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#376f7b"/></marker></defs>','<rect x="-1000" y="-100" width="5000" height="20000" fill="white"/>']
        for rel in sheet['relationships']:
            a,b,c,d=curve_geometry(rel,self.geometry)
            lines.append(f'<path d="M{a[0]},{a[1]} C{b[0]},{b[1]} {c[0]},{c[1]} {d[0]},{d[1]}" fill="none" stroke="#376f7b" stroke-width="2" marker-end="url(#arrow)"/>')
        for t in self.topics(sheet):
            r=self.geometry[t['id']];color=t['style']['properties']['svg:fill'];fs=int(t['style']['properties']['fo:font-size'][:-2])*1.333
            lines.append(f'<rect x="{r["x"]-r["width"]/2}" y="{r["y"]-r["height"]/2}" width="{r["width"]}" height="{r["height"]}" rx="10" fill="{color}" stroke="#aac0cc"/>')
            texts=t['title'].splitlines()
            for i,line in enumerate(texts):
                y=r['y']+(i-(len(texts)-1)/2)*28+7
                lines.append(f'<text x="{r["x"]}" y="{y}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="{fs}" fill="#173047">{html.escape(line)}</text>')
        return '\n'.join(lines+['</svg>'])


def markdown(graph, workbook):
    lines=['# 完整函数与调用清单','','调用方向：调用者 → 被调用者。此清单包含可视图隐藏的普通函数。','']
    for file in graph['files']:
        module=next(n for n in graph['nodes'] if n['type']=='reference' and n['file']==file['file'])
        lines += ['## '+file['file'],'',module['purpose'],'']
        for f in workbook.functions.values():
            if f['file']==file['file']:
                lines += [f"### {f['qualified']} · L{f['line']}",'',workbook.note(f),'']
    lines += ['## 未解析调用','','诊断条目可能是项目外调用、动态调用或静态歧义，不表示目标已确认。','']
    for d in graph['diagnostics']:
        lines.append(f"- {d['file']}:{d['line']} `{d['expression']}` — {d['reason']}")
    return '\n'.join(lines).encode('utf-8')
