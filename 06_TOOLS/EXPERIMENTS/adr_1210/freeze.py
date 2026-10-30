from common import *
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1210/compact';S=C/'snapshot';b=read(DES/'baseline.json')
changed={n:sha(S/n) for n,h in b['manifest']['files'].items() if sha(S/n)!=h};assert len(changed)==6
hashes={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if not any(n in v.get('files',{}) for n in changed):continue
 before=sha(p)
 for n,h in changed.items():
  if n in v['files']:v['files'][n]=h
 put(p,v);hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';text=p.read_text()
for before,after in hashes.items():text=text.replace(before,after)
p.write_text(text)
put(DES/'fixture-bindings.json',{'06_TOOLS/EXPERIMENTS/adr_1210/test_schema_factor.py':sha(Path(__file__).parent/'test_schema_factor.py')})
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');rev=c['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
f={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in rev['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':f,'candidate_revision':binding,'product_changes':changed})
m=read(ADR/'실험/manifest.json');m['design']['fixture_bindings']=bind(DES/'fixture-bindings.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='compact',experiment_id=m['experiment_id'],arm_id='compact',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print('Frozen',len(f),'files; product',len(changed),'pin',len(hashes)+1)
