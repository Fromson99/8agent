from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0726/compact';C=B/'snapshot';A=R/'04_EXPERIMENTS/ADR/ADR-0726-lossless-navigation-input'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for name in ['02_BACKEND/semantic_runtime/legal_agent/wire_schema.py','05_TESTS/CONTRACTS/test_navigation_input_compaction.py']:
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(B),'--target',name,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text());files=v.get('files',{})
 if '02_BACKEND/semantic_runtime/legal_agent/local_gemma.py' in files:files['02_BACKEND/semantic_runtime/legal_agent/wire_schema.py']=sha(C/'02_BACKEND/semantic_runtime/legal_agent/wire_schema.py')
 for name in files:
  if (C/name).is_file():files[name]=sha(C/name)
 put(p,v)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(B)],check=True)
m=json.loads((A/'실험/manifest.json').read_text());cm=json.loads((B/'candidate.json').read_text());rev=cm['revisions'][-1]
m['design']['code_isolation']['candidates']=[{'candidate_id':'compact','arm_id':'compact','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((B/'candidate.json').relative_to(R)),'manifest_sha256':sha(B/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0726/run_contracts.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0726/run_contracts.py')}];put(A/'실험/manifest.json',m)
