from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0767-polished-narrative-qualification'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0767/polished';S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
cm=read(C/'candidate.json')
name='05_TESTS/CONTRACTS/test_narrative_answer.py'
if name not in {x['target_path'] for x in cm['files']}:
    subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',name,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
new='02_BACKEND/semantic_runtime/legal_agent/narrative_answer.py'
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
    v=read(p)
    if '02_BACKEND/semantic_runtime/legal_agent/completion_execution.py' in v.get('files',{}):v['files'][new]=sha(S/new)
    for name in v.get('files',{}):
        if (S/name).is_file():v['files'][name]=sha(S/name)
    put(p,v)
def refresh(x):
    if isinstance(x,dict):
        for k,val in list(x.items()):
            if isinstance(val,str) and len(val)==64 and (S/k).is_file():x[k]=sha(S/k)
            elif isinstance(val,str) and (S/val).is_file():
                for key in (k+'_sha256','sha256'):
                    if key in x and isinstance(x[key],str) and len(x[key])==64:x[key]=sha(S/val)
            elif isinstance(val,(dict,list)):refresh(val)
    elif isinstance(x,list):
        for row in x:refresh(row)
p=S/'00_SYSTEM/PIPELINE.json';v=read(p);refresh(v);put(p,v)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];m=read(A/'실험/manifest.json')
m['design']['code_isolation']['candidates']=[{'candidate_id':'polished','arm_id':'polished','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0767/run_case.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0767/run_case.py')}]
put(A/'실험/manifest.json',m)
print(C/'revisions'/rev['revision_id']/'snapshot')
