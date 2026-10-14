from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0772-source-provider-display';C=R/'02_BACKEND/lawrag/research/candidates/adr_0772/provider-display';S=C/'snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
c=read(C/'candidate.json');rev=c['revisions'][-1];m=read(A/'실험/manifest.json')
m['design']['code_isolation']['candidates']=[{'candidate_id':'provider-display','arm_id':'provider-display','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0772/run_tests.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0772/run_tests.py')}]
put(A/'실험/manifest.json',m);print(rev['revision_id'])
