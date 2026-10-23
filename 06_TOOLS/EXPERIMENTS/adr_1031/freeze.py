from common import *
from datetime import datetime, timezone
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
s=read(ART/'stage.json');d=ROOT/s['candidate_dir'];c=ROOT/s['root']
ac.freeze(d);assert not ac.validate(d)
manifest=read(d/'candidate.json');revision=manifest['revisions'][-1]
m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{
 'candidate_id':manifest['candidate_id'],'arm_id':'candidate','experiment_id':m['experiment_id'],'run_ids':['run-001'],
 'manifest_path':str((d/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(d/'candidate.json'),
 'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
 'runner_path':'06_TOOLS/EXPERIMENTS/adr_1031/run_contracts.py','runner_sha256':sha(Path(__file__).with_name('run_contracts.py'))}])
m['dataset'].update(name='Synthetic implementation contract fixtures',version='small-connections-v1',
 frozen_source=str((c/'05_TESTS/CONTRACTS/test_small_connection_context_api.py').relative_to(ROOT)),
 sha256=sha(c/'05_TESTS/CONTRACTS/test_small_connection_context_api.py'),legal_version_checked=False,reference_version_checked=False)
save(ADR/'실험/manifest.json',m)
save(ART/('design-'+revision['revision_id']+'.json'),{'frozen_at':datetime.now(timezone.utc).isoformat(),
 'design':m['design'],'manifest_sha256':sha(ADR/'실험/manifest.json'),
 'files':{str(p.relative_to(c)):sha(p) for p in c.rglob('*') if p.is_file() and '__pycache__' not in p.parts},
 'runner_sha256':sha(Path(__file__).with_name('run_contracts.py')),'live_model_calls':0})
print(revision['revision_id'])
