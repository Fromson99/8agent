from common import *
import ast
S=CAND/'snapshot';b=read(DES/'baseline.json')
changes={n:sha(S/n) for n,h in b['manifest']['files'].items() if sha(S/n)!=h}
assert len(changes)==3
for n in changes:ast.parse((S/n).read_text())
hashes={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if not set(changes)&set(v.get('files',{})):continue
 before=sha(p);v['files'].update(changes);put(p,v);hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';s=p.read_text()
for old,new in hashes.items():s=s.replace(old,new)
p.write_text(s)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
bindings=[]
for candidate in (CAND,PORT):
 ac.freeze(candidate);assert not ac.validate(candidate)
 v=read(candidate/'candidate.json')['revisions'][-1];code=candidate/'revisions'/v['revision_id']/'snapshot'
 pin={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
 f={'code_root':str(code.relative_to(ROOT)),'files':{str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']},'candidate_revision':pin,'product_changes':changes if candidate==CAND else None}
 put(DES/('freeze.json' if candidate==CAND else 'port-freeze.json'),f)
 bindings.append(dict(pin,candidate_id=candidate.name,experiment_id=read(ADR/'실험/manifest.json')['experiment_id'],arm_id='repaired',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py')))
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=bindings)
put(ADR/'실험/manifest.json',m)
print('Frozen',len(read(DES/'freeze.json')['files']),'engine files and',len(read(DES/'port-freeze.json')['files']),'port files')
