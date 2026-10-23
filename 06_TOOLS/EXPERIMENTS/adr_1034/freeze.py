from common import *
from datetime import datetime, timezone
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
s=read(ART/'stage.json');m=read(ADR/'실험/manifest.json')
assert not (ART/'design-freeze.json').exists()
candidates=[];files={}
for arm, directory in s['candidate_dirs'].items():
    d=ROOT/directory;c=d/'snapshot'
    ac.freeze(d);assert not ac.validate(d)
    revision=read(d/'candidate.json')['revisions'][-1]
    candidates.append({'candidate_id':read(d/'candidate.json')['candidate_id'],'arm_id':arm,'experiment_id':m['experiment_id'],'run_ids':['run-001'],
        'manifest_path':str((d/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(d/'candidate.json'),
        'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
        'runner_path':'06_TOOLS/EXPERIMENTS/adr_1034/guard.py','runner_sha256':sha(Path(__file__).with_name('guard.py'))})
    files[arm]={str(p.relative_to(c)):sha(p) for p in c.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=candidates)
m['dataset'].update(name='Known public capital-gains question',version='20261023-read-judgment-live-question-v1',frozen_source=str((ART/'known-request.json').relative_to(ROOT)),sha256=sha(ART/'known-request.json'),legal_version_checked=True,reference_version_checked=False,version_scope='Same exact public MAIN102 corpus; no approved answer gold, no freshness/current-law claim.')
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
save(ADR/'실험/manifest.json',m)
save(ART/'design-freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'design':m['design'],
    'manifest_sha256':sha(ADR/'실험/manifest.json'),'request_sha256':sha(ART/'known-request.json'),
    'files':files,'runner_hashes':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},
    'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py'),
    'equal_operational_overrides':{'max_model_attempts':14,'max_transport_retries':0,'wall_seconds':1800},
    'arm_order':s['arm_order'],'live_model_calls_before_freeze':0})
print('Frozen', {a:len(v) for a,v in files.items()})
