from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0845/terminal';S=C/'snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
W=S/'02_BACKEND/workflow';p=W/'risk_team_compare_workflow/manifest.json';v=json.loads(p.read_text());v['files']={n:sha(W/n) for n in v['files']};put(p,v)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if 'files' in v:v['files']={n:sha(S/n) for n in v['files']};put(p,v)
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
for w in v['workflows']['registered']:w['sha256']=sha(S/w['manifest'])
put(p,v)
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True)
