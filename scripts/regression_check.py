"""Read-only source regression with source-byte and call-count evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/code-function-mind-map/scripts'))
from code_map import build
from model import load,scan_files,write


def snapshot(source,output):
    return {p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in scan_files(source,output,[])}


def regression(source,output,baseline):
    before=snapshot(source,output)
    report=build(source,output)
    after=snapshot(source,output)
    if before!=after:raise AssertionError('Regression modified source files')
    evidence={'source_unchanged':True,'source_files_hashed':len(before),'result':report}
    if baseline:
        nav=load(baseline/'navigation-index.json');old=load(baseline/'frontend-function-call-mindmap.json')
        new=load(output/'auxiliary/data/graph.json')
        old_names={}
        for key,location in nav['functions'].items():
            file,rest=key.split('::',1);name,position=rest.rsplit('@',1)
            old_names[location['canonical_id']]=(file,int(position.split(':')[0]),name.rsplit('.',1)[-1])
        new_names={n['id']:(n['file'],n['line'],n['name'].rsplit('.',1)[-1]) for n in new['nodes'] if n['type']=='function'}
        old_edges={(old_names[e['from']],old_names[e['to']]) for e in old['edges'] if e['type']!='tree'}
        new_edges={(new_names[e['from']],new_names[e['to']]) for e in new['edges'] if e['type']!='tree'}
        evidence.update(added_functions=sorted(set(new_names.values())-set(old_names.values())),removed_functions=sorted(set(old_names.values())-set(new_names.values())),added_calls=sorted(new_edges-old_edges),removed_calls=sorted(old_edges-new_edges))
    write(output/'regression-evidence.json',evidence)
    print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--baseline-data',type=Path)
    args=parser.parse_args()
    regression(args.source.resolve(),args.output.resolve(),args.baseline_data)
