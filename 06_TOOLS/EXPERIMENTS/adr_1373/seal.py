"""Inventory immutable experiment evidence after all workers have ended."""
from common import *
files=[]
for base in (ART,ROOT/'06_TOOLS/EXPERIMENTS/adr_1373'):
 for p in sorted(base.rglob('*')):
  if not p.is_file() or '__pycache__' in p.parts or p==ART/'manifest.json':continue
  if p.parent.name=='.observer-versions' and p.name.startswith('manifest-'):continue
  files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved actual experiment observation, source audit, source review or runtime archive','contains_raw_prompts_and_outputs':('canonical' in p.parts or p.name in ('response.json.gz','request.json.gz','answer.txt','runtime.tar.gz'))})
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1373','files':files})
print('SEALED',len(files))
