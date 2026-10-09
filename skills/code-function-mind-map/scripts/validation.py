"""Validate files independently of the renderer; native rendering is separate."""
from collections import Counter
from pathlib import Path
import json
import zipfile
from model import load, uid
from render import curve_geometry, hits, crosses_endpoint


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_graph(graph):
    nodes={n['id']:n for n in graph['nodes']}
    require(len(nodes)==len(graph['nodes']),'Duplicate canonical ID')
    roots=[n['id'] for n in nodes.values() if n['type']=='root']
    require(len(roots)==1,'Exactly one root is required')
    children={};parents=Counter();semantic=set()
    for e in graph['edges']:
        require(e['from'] in nodes and e['to'] in nodes,'Missing canonical edge endpoint')
        if e['type']=='tree':
            children.setdefault(e['from'],[]).append(e['to']);parents[e['to']]+=1
        else:
            require(nodes[e['from']]['type']==nodes[e['to']]['type']=='function','Call endpoint must be a function')
            semantic.add((e['from'],e['to']))
    require(parents[roots[0]]==0,'Root cannot have a parent')
    require(all(parents[k]==1 for k in nodes if k!=roots[0]),'Canonical tree parent mismatch')
    seen=set();pending=[roots[0]]
    while pending:
        key=pending.pop()
        require(key not in seen,'Canonical tree cycle')
        seen.add(key);pending.extend(children.get(key,[]))
    require(seen==set(nodes),'Unreachable canonical node')
    require(len(semantic)==sum(e['type']!='tree' for e in graph['edges']),'Duplicate canonical calls')
    incoming=Counter(b for a,b in semantic);outgoing=Counter(a for a,b in semantic)
    for n in nodes.values():
        if n['type']=='function':
            require(n['incoming']==incoming[n['id']] and n['outgoing']==outgoing[n['id']],'Function degree mismatch')
    for e in graph['bindings']:
        require(e['from'] in nodes and e['to'] in nodes,'Missing callback endpoint')
    return semantic


def validate_output(output: Path):
    graph=load(output/'auxiliary/data/graph.json');semantic=validate_graph(graph)
    nav=load(output/'auxiliary/data/navigation-index.json')
    with zipfile.ZipFile(output/'code-function-call-mindmap.xmind') as archive:
        require(archive.testzip() is None,'Corrupt XMind ZIP')
        require({'content.json','metadata.json','manifest.json'}<=set(archive.namelist()),'Incomplete XMind ZIP')
        sheets=json.loads(archive.read('content.json'));meta=json.loads(archive.read('metadata.json'))
    require(sheets and meta['activeSheetId']==sheets[0]['id'],'Directory is not active')
    ids=set();topic_ids=set();links=[];topics=0;relationships=0
    topic_objects={};topic_sheets={};relation_objects={}
    all_functions={n['id'] for n in graph['nodes'] if n['type']=='function'}
    require(set(nav['functions'])==all_functions,'Navigation function coverage mismatch')
    require(set(nav['visible_functions'])|set(nav['hidden_functions'])==all_functions,'Visible/hidden partition mismatch')
    require(not set(nav['visible_functions']) & set(nav['hidden_functions']),'Visible/hidden overlap')
    geometry=nav['geometry'];roles=nav['topic_roles']
    for sheet in sheets:
        nodes=[sheet['rootTopic'],*sheet['rootTopic'].get('children',{}).get('detached',[])]
        boxes={n['id']:geometry[n['id']] for n in nodes}
        visual_count=sum(roles[n['id']] in {'function','caller_reference'} for n in nodes)
        reference_count=sum(roles[n['id']]=='target_reference' for n in nodes)
        require(visual_count<=24,'Page function count exceeded')
        require(reference_count+len(sheet['relationships'])<=40,'Page relationship count exceeded')
        for obj in [sheet,*nodes,*sheet['relationships']]:
            for identity in [obj['id'],*([obj['style']['id']] if 'style' in obj else [])]:
                require(identity not in ids,'Duplicate XMind ID: '+identity);ids.add(identity)
        for n in nodes:
            topic_ids.add(n['id']);topics+=1
            topic_objects[n['id']]=n;topic_sheets[n['id']]=sheet['id']
            require(n['position']=={'x':geometry[n['id']]['x'],'y':geometry[n['id']]['y']},'XMind/navigation position mismatch')
            require(n['customWidth']==geometry[n['id']]['width'],'XMind/navigation width mismatch')
            if n.get('href'):
                require(n['href'].startswith('xmind:#'),'Unexpected navigation URL')
                links.append(n['href'][7:])
            if roles[n['id']] in {'function','caller_reference'}:
                require(int(n['style']['properties']['fo:font-size'][:-2])>=16,'Function font is too small')
                require(geometry[n['id']]['height']<=90,'Function card is too tall')
        for i,a in enumerate(nodes):
            x=boxes[a['id']]
            for b in nodes[i+1:]:
                y=boxes[b['id']]
                require(not(abs(x['x']-y['x'])<(x['width']+y['width'])/2 and abs(x['y']-y['y'])<(x['height']+y['height'])/2),'Overlapping nodes in '+sheet['title'])
        paths=[]
        for r in sheet['relationships']:
            relation_objects[r['id']]=r
            require(r['end1Id'] in boxes and r['end2Id'] in boxes,'Cross-page XMind line')
            points=curve_geometry(r,geometry)
            require(points not in paths and list(reversed(points)) not in paths,'Coincident XMind lines');paths.append(points)
            require(not hits(points,boxes,{r['end1Id'],r['end2Id']}),'Curve crosses another node')
            require(not crosses_endpoint(points,boxes,{r['end1Id'],r['end2Id']}),'Curve crosses an endpoint body')
            relationships+=1
        canvas=load(output/('auxiliary/canvas/'+sheet['id']+'.canvas'))
        require({n['id'] for n in canvas['nodes']}==set(boxes),'Canvas/XMind nodes differ')
        require({e['id'] for e in canvas['edges']}=={e['id'] for e in sheet['relationships']},'Canvas/XMind relationships differ')
        for n in canvas['nodes']:
            box=boxes[n['id']]
            require(n['text']==topic_objects[n['id']]['title'],'Canvas/XMind text mismatch')
            require((n['x'],n['y'],n['width'],n['height'])==(box['x']-box['width']/2,box['y']-box['height']/2,box['width'],box['height']),'Canvas geometry mismatch')
        for e in canvas['edges']:
            require(e['fromNode'] in boxes and e['toNode'] in boxes,'Invalid Canvas endpoint')
            relation=relation_objects[e['id']]
            require((e['fromNode'],e['toNode'])==(relation['end1Id'],relation['end2Id']),'Canvas relationship endpoint mismatch')
    require(all(k in topic_ids for k in links),'Invalid navigation target')
    for key,location in nav['functions'].items():
        if location['visible']:
            require(location['topic_id'] in topic_ids,'Missing primary function topic')
            require(topic_sheets[location['topic_id']]==location['sheet_id'],'Primary function sheet mismatch')
            require(location['topic_id']==uid('topic',location['sheet_id']+':'+key),'Primary function identity mismatch')
            require(roles[location['topic_id']]=='function','Primary function role mismatch')
    require(set(nav['relationship_source'])==set(relation_objects),'XMind/navigation relation mismatch')
    require(set(nav['reference_source'])=={k for k in topic_ids if roles[k]=='target_reference'},'XMind/navigation reference mismatch')
    for tid,(caller,target) in nav['reference_source'].items():
        require(tid==uid('topic',topic_sheets[tid]+':ref:'+caller+'>'+target),'Reference identity mismatch')
        require(topic_objects[tid].get('href')=='xmind:#'+nav['functions'][target]['topic_id'],'Reference does not link to its target function')
    for rid,(caller,target) in nav['relationship_source'].items():
        relation=relation_objects[rid]
        sheet=topic_sheets[relation['end1Id']]
        require((relation['end1Id'],relation['end2Id'])==(uid('topic',sheet+':'+caller),uid('topic',sheet+':'+target)),'XMind relationship/canonical endpoint mismatch')
    for key,location in nav['functions'].items():
        for sheet in sheets:
            tid=uid('topic',sheet['id']+':'+key)
            if tid in topic_objects and roles[tid]=='caller_reference':
                require(topic_objects[tid].get('href')=='xmind:#'+location['topic_id'],'Caller reference does not link to its primary function')
    home=sheets[0]['rootTopic']['id']
    for sheet in sheets[1:]:
        entry=uid('topic','link:'+sheet['id'])
        require(entry in topic_objects and topic_objects[entry].get('href')=='xmind:#'+sheet['rootTopic']['id'],'Directory module link mismatch')
        back=[n for n in [*sheet['rootTopic']['children']['detached']] if roles[n['id']]=='navigation']
        require(len(back)==1 and back[0].get('href')=='xmind:#'+home,'Return-to-directory link mismatch')
    visible=set(nav['visible_functions'])
    expected={(a,b) for a,b in semantic if a in visible and b in visible}
    actual=Counter(tuple(p) for p in [*nav['relationship_source'].values(),*nav['reference_source'].values()])
    require(set(actual)==expected and all(v==1 for v in actual.values()),'Visible call/reference coverage mismatch')
    require(len(sheets)==len(nav['sheets']),'Navigation sheet count mismatch')
    return {'files':len(graph['files']),'functions':len(all_functions),'canonical_relationships':len(semantic),'visible_functions':len(visible),'hidden_functions':len(all_functions-visible),'sheets':len(sheets),'topics':topics,'visible_relationships':relationships,'target_references':len(nav['reference_source']),'internal_links':len(links),'diagnostics':len(graph['diagnostics']),'structure':'passed','geometry':'node rectangles and sampled curves passed','native_app_check':'not_run: actual XMind rendering/open-save-reopen was not verified'}
