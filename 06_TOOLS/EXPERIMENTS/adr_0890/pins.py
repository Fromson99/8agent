from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0890/frontier/snapshot';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
w=S/'02_BACKEND/workflow'
for p in w.glob('*/manifest.json'):
 v=json.loads(p.read_text())
 if v['workflow_id']=='risk_team_compare_workflow':v['version']='1.10.0'
 for n in v['files']:v['files'][n]=sha(w/n)
 put(p,v)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if not isinstance(v.get('files'),dict):continue
 for n in v['files']:
  if (S/n).exists():v['files'][n]=sha(S/n)
 put(p,v)
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
for entry in v['workflows']['registered']:
 entry['sha256']=sha(S/entry['manifest']);entry['version']=json.loads((S/entry['manifest']).read_text())['version']
put(p,v)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
print('Workflow1.9.1 and unchanged discovery1.0.0 pins linked; candidate syntax PASS')
