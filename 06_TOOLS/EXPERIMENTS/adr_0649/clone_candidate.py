"""Clone completed frozen research code with fresh upstream provenance."""
import argparse,json,subprocess,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--adr',required=True);p.add_argument('--number',required=True);p.add_argument('--id',required=True);p.add_argument('--parent',required=True);p.add_argument('--overlay',action='append',default=[]);a=p.parse_args();parent=R/a.parent;m=json.loads((parent/'candidate.json').read_text());files={x['target_path']:parent/'revisions'/m['revisions'][-1]['revision_id']/'snapshot'/x['target_path'] for x in m['files']}
for overlay in a.overlay:
 c=R/overlay;o=json.loads((c/'candidate.json').read_text())
 for x in o['files']:files[x['target_path']]=c/'revisions'/o['revisions'][-1]['revision_id']/'snapshot'/x['target_path']
args=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',a.adr,'--candidate-id',a.id,'--experiment-id','ADR-'+a.number+'-experiment-v1','--arm-id',a.id,'--run-id','run-001']
for t in files:
 if (R/t).exists():args+=['--source',t]
r=subprocess.run(args,capture_output=True,text=True);assert r.returncode==0,r.stderr
C=R/'02_BACKEND/lawrag/research/candidates'/('adr_'+a.number)/a.id
for t,f in files.items():
 out=C/'snapshot'/t;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,out)
 if not (R/t).exists():
  r=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',t,'--upstream-state','absent'],capture_output=True,text=True);assert r.returncode==0,r.stderr
print(C,len(files))
