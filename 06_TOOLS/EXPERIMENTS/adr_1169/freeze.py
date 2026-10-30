from common import *
import sys
T=Path(__file__).parent;C=ROOT/read(DES/'candidate.json')['root'];S=C/'snapshot'
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1167-supervisor-route-identity/artifacts/design/freeze.json')
assert all(sha(S/n)==h for n,h in parent['files'].items())
for p in T.glob('*.py'):compile(p.read_text(),str(p),'exec')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');v=c['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';files={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']};assert files==parent['files']
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='supervised',experiment_id=m['experiment_id'],arm_id='supervised',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))]);put(ADR/'실험/manifest.json',m)
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':files,'candidate_revision':binding,'pointer_sha256':parent['pointer_sha256'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json') if p.name!='freeze.json'},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')},'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')})
print('Frozen',v['revision_id'],len(files),'exact parent files; model0')
