from pathlib import Path
import hashlib,json,sys
R=Path(__file__).resolve().parents[3]
C=Path(sys.argv[1]) if len(sys.argv)>1 else R/'02_BACKEND/lawrag/research/candidates/adr_0791/orchestration/snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=C/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json';m=json.loads(p.read_text())
m['files']={k:sha(C/'02_BACKEND/workflow'/k) for k in m['files']};put(p,m)
p=C/'00_SYSTEM/PIPELINE.json';m=json.loads(p.read_text())
m['workflows']['registered'][0]['sha256']=sha(C/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if 'files' not in v:continue
 v['files']={k:sha(C/k) for k in v['files']};put(p,v)
for v in m['engines'].values():v['sha256']=sha(C/v['manifest'])
put(C/'00_SYSTEM/PIPELINE.json',m)
