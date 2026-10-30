from common import *
import ast
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1229/meaning-evidence';S=C/'snapshot';b=read(DES/'baseline.json');parent=read(DES/'parent-candidate.json')
changes={n:sha(S/n) for n in parent['product_changes']}
for n in changes:ast.parse((S/n).read_text())
hashes={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if not set(changes)&set(v.get('files',{})):continue
 before=sha(p);v['files'].update(changes);put(p,v);hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';s=p.read_text()
for before,after in hashes.items():s=s.replace(before,after)
p.write_text(s)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
f={'code_root':str(code.relative_to(ROOT)),'files':{str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']},'candidate_revision':binding,'product_changes':changes}
put(DES/'freeze-current.json',f);put(DES/'fixture-bindings.json',{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='meaning-evidence',experiment_id=m['experiment_id'],arm_id='meaning-evidence',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print('Frozen489, source meaning/evidence only delta from1227')
