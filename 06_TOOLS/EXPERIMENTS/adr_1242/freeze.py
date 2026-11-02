from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1242-oracle-agent-records-main';D=ADR/'artifacts/design'
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1242/oracle-records';S=C/'snapshot'
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
put=lambda p,v:Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'baseline.json')
workflow_hashes={}
for p in (S/'02_BACKEND/workflow').rglob('manifest.json'):
 v=read(p)
 if not isinstance(v.get('files'),dict):continue
 before=sha(p)
 for name in v['files']:v['files'][name]=sha(S/'02_BACKEND/workflow'/name)
 put(p,v);workflow_hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';text=p.read_text()
for old,new in workflow_hashes.items():text=text.replace(old,new)
p.write_text(text)
changes={str(p.relative_to(S)):sha(p) for p in S.rglob('*') if p.is_file() and
         (str(p.relative_to(S)) not in b['manifest']['files'] or sha(p)!=b['manifest']['files'][str(p.relative_to(S))])}
changes={n:h for n,h in changes.items() if n!='00_SYSTEM/PIPELINE.json' and not n.startswith('02_BACKEND/ENGINES/')}
for name in changes:
 if name.endswith('.py'):ast.parse((S/name).read_text())
hashes={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if not set(changes)&set(v.get('files',{})):continue
 before=sha(p);v['files'].pop('service.py',None)
 v['files'].update({n:h for n,h in changes.items() if n!='service.py'})
 put(p,v);hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';text=p.read_text()
for old,new in hashes.items():text=text.replace(old,new)
p.write_text(text)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot'
pin={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),
     'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(D/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':{str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']},
    'candidate_revision':pin,'product_changes':changes})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,
    candidates=[dict(pin,candidate_id='oracle-records',experiment_id=m['experiment_id'],arm_id='oracle-records',run_ids=['run-001'],
                    runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))])
put(ADR/'실험/manifest.json',m)
print('Frozen Oracle records candidate:',v['revision_id'],'files',len(v['files']),'product changes',len(changes))
