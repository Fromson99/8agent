from common import *
import ast
assert not (DES/'freeze.json').exists()
candidate=read(DES/'candidate.json');T=Path(__file__).parent
for p in T.glob('*.py'):ast.parse(p.read_text())
paths=list(DES.glob('*.json'))+list((ART/'gold-connector').glob('*'))+list((ART/'transport').rglob('*.py'))+[ART/'transport/transport-pins.json']+list(T.glob('*.py'))
paths += [ROOT/p for p in read(DES/'comparison-source.json')['files']]
binding=read(ART/'gold-connector/binding.json');paths += [ROOT/p for p in binding['files']]
paths += [ROOT/read(DES/'baseline.json')['pointer']['manifest_path']]
put(DES/'freeze.json',{'frozen_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'code_root':candidate['code_root'],'selected_files':candidate['selected_files'],'candidate':candidate['pin'],'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.is_file()},'model_calls_before_freeze':0})
m=read(ADR/'실험/manifest.json');pin=candidate['pin']
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{**pin,'candidate_id':'selected-main133','experiment_id':m['experiment_id'],'arm_id':'ontology-on','run_ids':['run-001'],'runner_path':str((T/'live.py').relative_to(ROOT)),'runner_sha256':sha(T/'live.py')}])
put(ADR/'실험/manifest.json',m)
print('FROZEN',len(read(DES/'freeze.json')['files']),'support files; selected513 unchanged')

