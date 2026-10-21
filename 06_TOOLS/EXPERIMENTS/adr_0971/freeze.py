from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
assert not (DES/'freeze.json').exists()
source=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0971/dense-rerank/snapshot'/TARGET
dest=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0971/dense/snapshot'/TARGET;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
m=read(ADR/'실험/manifest.json');candidates=[]
for arm in ['dense','dense-rerank']:
 c=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0971'/arm
 ac.register_file(c,TARGET,upstream_state='absent');ac.freeze(c);assert not ac.validate(c)
 cm=read(c/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('run.py')
 candidates.append({'candidate_id':arm,'arm_id':arm,'experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((c/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(c/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=candidates)
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
data=ROOT/read(DES/'criteria.json')['generation_path']
inputs=[data/'store.sqlite',data/'manifest.json',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'02_BACKEND/lawrag/research/experiment_client.py',ROOT/'01_DATA/GOLDEN/registry-v2-risk_cm.json']+list(DES.glob('*.json'))+list(Path(__file__).parent.glob('*.py'))
put(DES/'freeze.json',{'files':{str(x.relative_to(ROOT)):sha(x) for x in inputs},'candidates':candidates,'model_calls_before_freeze':0})
print('Frozen70 scope, models, two candidate revisions and explicit runner.')
