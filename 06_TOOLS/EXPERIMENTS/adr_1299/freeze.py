from common import *
import ast
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
candidate=ROOT/read(DES/'candidate.json')['path'];ac.freeze(candidate);assert not ac.validate(candidate)
v=read(candidate/'candidate.json')['revisions'][-1];C=candidate/'revisions'/v['revision_id']/'snapshot'
files={str((ROOT/x['frozen_path']).relative_to(C)):x['snapshot_sha256'] for x in v['files']}
pin={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
T=Path(__file__).parent
for p in T.glob('*.py'):ast.parse(p.read_text())
inputs=read(DES/'inputs.json')['files'];inputs.update({str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json')})
inputs['06_TOOLS/maintenance/experiment_json.py']=sha(ROOT/'06_TOOLS/maintenance/experiment_json.py')
inputs[str((ART/'preflight/result.json').relative_to(ROOT))]=sha(ART/'preflight/result.json')
put(DES/'freeze.json',{'code_root':str(C.relative_to(ROOT)),'files':files,'candidate_revision':pin,
 'pointer_sha256':read(DES/'selected.json')['pointer_sha256'],'inputs':inputs,
 'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')},'external_calls':False,'oracle_access':False})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='verified',experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'],runner_path=str((T/'probe.py').relative_to(ROOT)),runner_sha256=sha(T/'probe.py'))]);put(ADR/'실험/manifest.json',m)
print('Frozen',v['revision_id'],len(files))
