from common import *
import sys
C=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/read(ART/'stage.json')['root']
changed=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('read_judgment.py','decision_projection.py','output_contract.py')]
pins={}
for path in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(path)
 if 'files' not in v:continue
 before=sha(path)
 for name in changed:
  if name in v['files'] or (name.endswith(('/read_judgment.py','/read_judgment_final.py')) and '02_BACKEND/semantic_runtime/legal_agent/decision_projection.py' in v['files']):v['files'][name]=sha(C/name)
 if v!=read(path):save(path,v);pins[str(path.relative_to(C))]={'before':before,'after':sha(path)}
p=C/'00_SYSTEM/PIPELINE.json';v=read(p);before=sha(p)
for engine in v['engines'].values():
 if engine['manifest'] in pins:engine['sha256']=sha(C/engine['manifest'])
if v!=read(p):save(p,v);pins[str(p.relative_to(C))]={'before':before,'after':sha(p)}
checked=0
for path in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 for name,expected in read(path).get('files',{}).items():
  assert sha(C/name)==expected,name
  checked+=1
for engine in v['engines'].values():assert sha(C/engine['manifest'])==engine['sha256']
save(ART/('working-pins.json' if C==ROOT else 'candidate-pins.json'),{'checked':checked,'changes':pins})
print('Verified pins',checked)
