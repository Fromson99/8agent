"""Retain concurrent basis lifecycle work, with a new candidate provenance."""
from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0850-minimal-output-qualification';D=A/'artifacts/design'
old=R/'02_BACKEND/lawrag/research/candidates/adr_0850/qualified';C=old.with_name('rebased');S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not C.exists()
cm=read(old/'candidate.json');names={x['target_path'] for x in cm['files'] if x['upstream_state']=='present'}
for p in (R/'02_BACKEND/ENGINES').rglob('*.json'):
 names.add(str(p.relative_to(R)));names.update(read(p).get('files',{}))
for w in read(R/'00_SYSTEM/PIPELINE.json')['workflows']['registered']:
 names.add(w['manifest']);names.update('02_BACKEND/workflow/'+n for n in read(R/w['manifest']).get('files',{}))
new='02_BACKEND/semantic_runtime/legal_agent/minimal_output.py';names.discard(new)
assert all((R/n).is_file() for n in names)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','rebased','--experiment-id','ADR-0850-experiment-v1','--arm-id','qualified','--run-id','run-001']
for n in sorted(names):cmd+=['--source',n]
subprocess.run(cmd,cwd=R,check=True)
before={n:sha(R/n) for n in names};before[new]=None
changed=[]
for x in cm['files']:
 n=x['target_path']
 if n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/'):continue
 if x['upstream_state']=='absent' or sha(old/'snapshot'/n)!=x['upstream_sha256']:
  changed.append(n)
  if n=='02_BACKEND/semantic_runtime/workflow_bridge.py':
   p=S/n;s=p.read_text();anchor='        value=strict_json(structured_content(body,require_complete=True))\n'
   assert s.count(anchor)==1 and 'minimal_output' not in s
   p.write_text(s.replace(anchor,anchor+'        from .legal_agent.minimal_output import Projection\n        value=Projection(schema).expand(value)\n'))
  else:
   assert x['upstream_state']=='absent' or sha(R/n)==x['upstream_sha256'],('overlapping unreviewed implementation',n)
   (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old/'snapshot'/n,S/n)
subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',new,'--upstream-state','absent'],cwd=R,check=True)
put(D/'working-rebased-before.json',before)
put(D/'baseline-rebased.json',{'pointer':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
put(D/'rebase.json',{'reason':'Concurrent ADR0849 working integration invalidated initial upstream before freeze. No qualified run occurred on that candidate.',
 'original_candidate':str(old.relative_to(R)),'candidate':str(C.relative_to(R)),'reviewed_changes':changed,
 'overlap':'workflow_bridge: only insert minimal decoder in recover_response; retain all basis methods and question fallback',
 'preserved_new_dependencies':sorted(names-{x['target_path'] for x in cm['files']})})
for name in ('run_tests.py','repin.py','freeze.py'):
 p=Path(__file__).parent/name;s=p.read_text().replace('adr_0850/qualified','adr_0850/rebased')
 if name=='freeze.py':s=s.replace("'candidate_id':'qualified'","'candidate_id':'rebased'")
 p.write_text(s)
print('New candidate retains current working code; changed implementation files:',len(changed))
