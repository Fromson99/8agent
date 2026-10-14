from pathlib import Path
import json,hashlib,subprocess
R=Path(__file__).resolve().parents[3];B=R/'02_BACKEND/lawrag/research/candidates/adr_0759/integrated';C=B/'snapshot';A=R/'04_EXPERIMENTS/ADR/ADR-0759-query-routing-native-contract'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ['navigation_input','completion_v6','completion_v7','completion_v8','investigation_scope']]
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text());files=v.get('files',{})
 if '02_BACKEND/semantic_runtime/legal_agent/completion_v5.py' in files:
  for name in new:files[name]=sha(C/name)
 for name in files:
  if (C/name).is_file():files[name]=sha(C/name)
 put(p,v)
p=C/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
def refresh(x):
 if isinstance(x,dict):
  for k,val in list(x.items()):
   if isinstance(val,str) and len(val)==64 and (C/k).is_file():x[k]=sha(C/k)
   elif isinstance(val,str) and (C/val).is_file():
    for key in (k+'_sha256','sha256'):
     if key in x and isinstance(x[key],str) and len(x[key])==64:x[key]=sha(C/val)
   elif isinstance(val,(dict,list)):refresh(val)
 elif isinstance(x,list):
  for row in x:refresh(row)
refresh(v);put(p,v)
p=R/'06_TOOLS/EXPERIMENTS/adr_0759/run_contracts.py'
s=(R/'06_TOOLS/EXPERIMENTS/adr_0729/run_contracts.py').read_text().replace('adr_0729/compact','adr_0759/integrated').replace('ADR-0729-compact-branch-choice-contract','ADR-0759-query-routing-native-contract')
s=s.replace("str(code/'05_TESTS/CONTRACTS/test_navigation_input_compaction.py')]", "str(code/'05_TESTS/CONTRACTS/test_navigation_input_compaction.py'),str(code/'05_TESTS/CONTRACTS/test_focused_input_modality.py'),str(code/'05_TESTS/CONTRACTS/test_single_rule_content.py'),str(code/'05_TESTS/CONTRACTS/test_source_span_norm.py')]")
p.write_text(s)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(B)],check=True,stdout=subprocess.DEVNULL)
cm=json.loads((B/'candidate.json').read_text());rev=cm['revisions'][-1];m=json.loads((A/'실험/manifest.json').read_text())
m['design']['code_isolation']['candidates']=[{'candidate_id':'integrated','arm_id':'integrated','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((B/'candidate.json').relative_to(R)),'manifest_sha256':sha(B/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(p.relative_to(R)),'runner_sha256':sha(p)}];put(A/'실험/manifest.json',m)
print('frozen',rev['revision_id'],len(rev['files']))
