from common import *
import ast,datetime
candidate=read(DES/'candidate.json');T=Path(__file__).parent
assert not (DES/'freeze.json').exists()
for p in T.glob('*.py'):ast.parse(p.read_text())
paths=list(DES.glob('*.json'))+list((ART/'transport').rglob('*.py'))+[ART/'transport/transport-pins.json']+list(T.glob('*.py'))
paths+=[ROOT/read(DES/'baseline.json')['pointer']['manifest_path']]
put(DES/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'code_root':candidate['code_root'],'selected_files':candidate['selected_files'],'candidate':candidate['pin'],'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'model_calls_before_freeze':0})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{**candidate['pin'],'candidate_id':'selected-main','experiment_id':m['experiment_id'],'arm_id':'selected-main','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(ROOT)),'runner_sha256':sha(T/'live.py')}]);put(ADR/'실험/manifest.json',m)
print('Frozen R2 answer experiment')
