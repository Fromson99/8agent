import json,hashlib,subprocess,shutil
from pathlib import Path
R=Path.cwd()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while chunk:=f.read(8388608):h.update(chunk)
 return h.hexdigest()
for number,suffix,arm in [(521,'shared-reference-root-workflow','integrated'),(522,'scoped-reference-returns','guarded')]:
 A=R/f'04_EXPERIMENTS/ADR/ADR-{number:04}-{suffix}';C=R/f'02_BACKEND/lawrag/research/candidates/adr_{number:04}/{arm}'
 # Remove only failed local packaging copies created by this task; successful v4 stays pinned.
 if number==521:
  for name in ('review-package','review-package-v2','review-package-v3'):
   p=A/'artifacts'/name
   if p.exists():shutil.rmtree(p)
 files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and not any(x.startswith('review-package-') or x=='source-only-runtime' for x in p.relative_to(A/'artifacts').parts) and p.name not in ('manifest.json','validation-final.txt','graph-check.txt')]
 files += [A/'README.md',A/'PLAN.md',C/'candidate.json',R/'07_DOCS/REFERENCE/REPORTS/REFERENCE_EXPLORATION_IMPLEMENTATION_20260922.md']
 files += list((R/f'06_TOOLS/EXPERIMENTS/adr_{number:04}').glob('*.py'))
 files += [R/f['frozen_path'] for f in json.loads((C/'candidate.json').read_text())['revisions'][-1]['files']]
 manifest={'schema_version':'adr-artifacts-v1','adr_id':f'ADR-{number:04}','created_at':'2026-09-22','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Candidate, pinned input, raw audit output, test or completion report; no live model outputs.','contains_raw_prompts_and_outputs':False} for p in sorted(set(files))]}
 (A/'artifacts/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 with (A/'artifacts/validation-final.txt').open('w') as out:
  result=subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py','validate','--path',str(A.relative_to(R)),'--final'],stdout=out,stderr=subprocess.STDOUT)
 print(number,result.returncode,flush=True)
