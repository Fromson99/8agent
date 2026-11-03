from common import *
import ast,shutil
T=Path(__file__).parent
candidate=(ROOT/read(DES/'candidate-path.json')['snapshot']).parent
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
for p in T.glob('*.py'):ast.parse(p.read_text())
ac.freeze(candidate)
assert not ac.validate(candidate),ac.validate(candidate)
v=read(candidate/'candidate.json')['revisions'][-1]
C=candidate/'revisions'/v['revision_id']/'snapshot'
pin={'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),
     'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
files={str((ROOT/x['frozen_path']).relative_to(C)):x['snapshot_sha256'] for x in v['files']}
transport=ART/'transport';transport.mkdir(exist_ok=False)
modules={'lawrag':'02_BACKEND/lawrag/__init__.py','lawrag.core':'02_BACKEND/lawrag/core/__init__.py',
    'lawrag.research':'02_BACKEND/lawrag/research/__init__.py','lawrag.core.request_deadline':'02_BACKEND/lawrag/core/request_deadline.py',
    'lawrag.research.experiment_client':'02_BACKEND/lawrag/research/experiment_client.py',
    'lawrag.research.openrouter_legal_adapter':'02_BACKEND/lawrag/research/openrouter_legal_adapter.py'}
for relative in modules.values():
    source=C/relative
    if not source.exists():source=ROOT/relative
    dest=transport/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
put(transport/'transport-pins.json',{'modules':modules,'files':{n:sha(transport/n) for n in modules.values()}})
data=ROOT/read(DES/'source.json')['data_path']
paths=list(DES.glob('*.json'))+list(transport.rglob('*.py'))+[transport/'transport-pins.json',
    ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',
    ROOT/'06_TOOLS/maintenance/experiment_json.py']
paths+=list(data.rglob('*.sqlite'))+list(data.rglob('*manifest*.json'))
put(DES/'freeze.json',{'code_root':str(C.relative_to(ROOT)),'files':files,'candidate_revision':pin,
    'pointer_sha256':read(DES/'baseline.json')['pointer_sha256'],
    'inputs':{str(p.relative_to(ROOT)):sha(p) for p in paths},
    'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')},
    'main_promoted':False,'model_behavior_changed':False,
    'display_changed':['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']})
m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,
    candidate_id='verified',experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'],
    runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))])
m['design']['retrieval_stage_plan']['stages_by_arm']={'verified':[
    {'stage_id':'source','kind':'source','parent_stage_ids':[]},
    {'stage_id':'acquired','kind':'retrieve','parent_stage_ids':['source']},
    {'stage_id':'present','kind':'present','parent_stage_ids':['acquired']}]}
m['retrieval_accounting'].update(not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',
    artifact_path=str((ART/'retrieval-stage-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
put(ART/'preparation-tests.json',{'first_attempt':'pytest collection rejected reserved parameter name request; no tests/model calls executed',
    'correction':'Renamed test parameter to payload; no product change required',
    'final':{'passed':49,'failed':0,'scope':'GENOS new source-only10 and existing reference display39, same candidate file'},
    'observer_review':'Per-derivation immutable file, final calls/generations summary written once; no mutable reuse of write_summary'})
print('FROZEN',v['revision_id'],len(files))
