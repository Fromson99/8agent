from common import *
import ast,datetime
T=Path(__file__).parent
assert not (DES/'freeze.json').exists()
for p in T.glob('*.py'):ast.parse(p.read_text())
paths=list(DES.glob('*.json'))+list((ART/'transport').rglob('*.py'))+[ART/'transport/transport-pins.json']+[p for p in T.glob('*.py') if p.name not in ('finalize.py','archive_all_closed.py')]
paths += [ROOT/read(DES/('baseline-'+a+'.json'))['pointer']['manifest_path'] for a in ('before','after')]
put(DES/'freeze.json',{'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'model_calls_before_freeze':0})
m=read(ADR/'실험/manifest.json');pins=[]
for arm in ('before','after'):
 c=read(DES/('candidate-'+arm+'.json'));pins.append({**c['pin'],'candidate_id':arm,'experiment_id':m['experiment_id'],'arm_id':arm,'run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(ROOT)),'runner_sha256':sha(T/'live.py')})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=pins);put(ADR/'실험/manifest.json',m)
print('Frozen MAIN135/136 paired SQLite test; 0 model calls before freeze')
