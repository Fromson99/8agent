from pathlib import Path
import json,hashlib,sys,subprocess
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0832/connected';S=C/'snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
cm=json.loads((C/'candidate.json').read_text());known={x['target_path'] for x in cm['files']}
for p in sorted(S.rglob('*')):
 if p.is_file() and '__pycache__' not in p.parts and str(p.relative_to(S)) not in known:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',str(p.relative_to(S)),'--upstream-state','present' if (R/p.relative_to(S)).exists() else 'absent'],cwd=R,check=True,stdout=subprocess.DEVNULL)
p=S/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json';v=json.loads(p.read_text())
for f in ('risk_team_compare_workflow/task_board.py','risk_team_compare_workflow/comparison_fields.json'):v['files'][f]=sha(S/'02_BACKEND/workflow'/f)
v['files']={n:sha(S/'02_BACKEND/workflow'/n) for n in v['files']};put(p,v)
new=['02_BACKEND/semantic_runtime/comparison_research_bridge.py','02_BACKEND/semantic_runtime/legal_agent/comparison_research.py','02_BACKEND/workflow/risk_team_compare_workflow/task_board.py','02_BACKEND/workflow/risk_team_compare_workflow/comparison_fields.json']
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if 'files' not in v:continue
 if '02_BACKEND/semantic_runtime/workflow_rag.py' in v['files']:
  for n in new:v['files'][n]=sha(S/n)
 v['files']={n:sha(S/n) for n in v['files']};put(p,v)
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
for d in v['workflows']['registered']:d['version']='1.4.2';d['sha256']=sha(S/d['manifest'])
put(p,v)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
print('refreshed candidate pins')
