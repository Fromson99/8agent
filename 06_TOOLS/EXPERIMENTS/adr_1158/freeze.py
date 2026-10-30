from common import *
import sys,ast
T=Path(__file__).parent
for p in T.glob('*.py'):ast.parse(p.read_text())
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.freeze(CAND);assert not ac.validate(CAND),ac.validate(CAND)
c=read(CAND/'candidate.json');v=c['revisions'][-1];code=CAND/'revisions'/v['revision_id']/'snapshot'
files={str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in v['files']}
binding={'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id=CAND.name,experiment_id=m['experiment_id'],arm_id='connected',run_ids=['run-001'],runner_path=str((T/'check.py').relative_to(ROOT)),runner_sha256=sha(T/'check.py'))]);put(ADR/'실험/manifest.json',m)
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':files,'binding':binding,'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')},'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json') if p.name!='freeze.json'}})
print('FROZEN',len(files),'files')
