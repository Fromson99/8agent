"""Append lifecycle completion and hash final experiment evidence, never MAIN."""
import sys,json,hashlib,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3]
number=sys.argv[1] if len(sys.argv)>1 else '0523';suffix={'0523':'gemma-scoped-exploration-probe','0524':'gemma-fp8-scoped-retrieval'}[number]
A=R/f'04_EXPERIMENTS/ADR/ADR-{number}-{suffix}';C=R/f'02_BACKEND/lawrag/research/candidates/adr_{number}/transport'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8388608):h.update(b)
 return h.hexdigest()
m=json.loads((A/'실험/manifest.json').read_text());assert m['results']['status']=='complete'
if m['reservation']['status']!='completed':
 subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','status','--path',str(A.relative_to(R)),'--status','completed','--note','Bounded Gemma paired calls completed; failures and provider overload retained; no quality certification or MAIN change'],check=True)
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and not any(x=='runtime-guarded' or x=='__pycache__' for x in p.relative_to(A/'artifacts').parts) and p.name not in ('manifest.json','validation-final.txt','graph-check.txt')]
files += [A/'README.md',A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',C/'candidate.json']
files += list((R/f'06_TOOLS/EXPERIMENTS/adr_{number}').glob('*.py'))
files += [R/v['frozen_path'] for v in json.loads((C/'candidate.json').read_text())['revisions'][-1]['files']]
artifact={'schema_version':'adr-artifacts-v1','adr_id':'ADR-'+number,'created_at':'2026-09-22','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs, exact model sends/responses, usage, request journals and offline accounting. result.json splits large graph to graph.json.gz; reassembly recovers original bundle hash.','contains_raw_prompts_and_outputs':'/calls/' in str(p) or p.name=='trace.json.gz'} for p in sorted(set(files))]}
(A/'artifacts/manifest.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n')
with (A/'artifacts/validation-final.txt').open('w') as out:
 result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(A.relative_to(R)),'--final'],stdout=out,stderr=subprocess.STDOUT)
print('final validation',number,result.returncode);print((A/'artifacts/validation-final.txt').read_text())
