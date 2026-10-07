"""Create follow-up snapshot without changing completed parent or working tree."""
from pathlib import Path
import json,subprocess,shutil,hashlib
R=Path(__file__).resolve().parents[3];P=R/'02_BACKEND/lawrag/research/candidates/adr_0674/integrated';C=R/'02_BACKEND/lawrag/research/candidates/adr_0675/integrated';A=R/'04_EXPERIMENTS/ADR/ADR-0675-investigation-control-binding-closure'
files=json.loads((P/'candidate.json').read_text())['files'];cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id','ADR-0675-experiment-v1','--arm-id','integrated','--run-id','run-001']
for f in files:
 if (R/f['target_path']).is_file():cmd+=['--source',f['target_path']]
subprocess.run(cmd,cwd=R,check=True)
for f in files:
 t=f['target_path'];dst=C/'snapshot'/t;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/'revisions/rev-001/snapshot'/t,dst)
 if not (R/t).is_file():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',t,'--upstream-state','absent'],cwd=R,check=True,stdout=subprocess.DEVNULL)
S=C/'snapshot';active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text());release=json.loads((R/active['manifest_path']).read_text())
# Exact same approved public documents, destination and policy as active release.
p=S/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json';grant=json.loads((R/release['code_root']/p.relative_to(S)).read_text());grant['adapter_version']='public-json-schema-v2';p.write_text(json.dumps(grant,ensure_ascii=False,indent=2)+'\n')
p=S/'02_BACKEND/semantic_runtime/legal_agent/memory_rag.py';s=p.read_text();s=s.replace("            def select(system,data,schema,phase,timeout):\n                raw=self.invoke(system,data,schema,phase,timeout=timeout)","            def select(system,data,schema,phase,timeout):\n                from copy import deepcopy\n                wire=deepcopy(schema)\n                legacy=not self.control and not phase.startswith(('source-law-','source-reference-'))\n                if legacy and 'choices' in wire.get('properties',{}):\n                    item=wire['properties']['choices']['items']\n                    item['properties'].pop('status',None)\n                    item['required']=[k for k in item['required'] if k!='status']\n                raw=self.invoke(system,data,wire,phase,timeout=timeout)\n                if legacy:\n                    for item in raw.get('choices',[]):item.setdefault('status','ADOPT')")
p.write_text(s)
# Freeze no new bytes yet; ordinary contract verification precedes product evaluation.
D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True);shutil.copy2(R/'04_EXPERIMENTS/ADR/ADR-0674-investigation-control-integration/artifacts/design/working-integration.json',D/'integration.json')
print(C)
