from common import *
import shutil,ast
T=Path(__file__).parent
baseline=read(DES/'baseline.json');r=baseline['release'];C=ROOT/r['code_root'];pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
assert read(pointer)['generation']==128 and read(DES/'preflight.json')['passed']
assert all(sha(C/n)==h for n,h in r['files'].items())
criteria={'hypothesis':'Unchanged MAIN128 can complete the same article369 question through existing local SQLite source and SQLite journals, without Oracle record amplification or process crash.',
 'success':['API200 with nonempty final answer and fresh-process persisted answer equality','Question parts covered in final accepted assessment, with genuine limitations retained','Acquired and delivered original spans match frozen source, ACL violations0, native-to-wire request match','Physical calls equal reserved budget, no dispatch after UNKNOWN, no output cap','Process completes cleanup without crash; continuous resource limits respected; frozen release/data unchanged'],
 'failure':['Any completion, integrity, budget or resource gate fails; preserve failure and stop without automatic retry'],
 'limits':{'physical':40,'tools':1024,'wall_seconds':1800,'per_model_seconds':180,'min_start_available_GiB':5,'min_running_available_GiB':3,'max_RSS_GiB':4,'max_AS_GiB':6,'swap_growth_MiB':128,'min_disk_GiB':20},
 'sample':'Same previously observed question gold-369 once. In-sample probe, no accuracy or p95 certification.',
 'controls':'Question text, document ACL 7bbe815ff43b6635, selected MAIN128495, Qwen3.8 Parasail FP8 with confirmed429-only NearAI switch, unchanged prompts/validator/budgets.',
 'differences':'Original source and state use local SQLite; selected local generation has 1547 documents but request scope1; local ontology OFF instead of Gold ON/DB; local initial vector support is not equivalent to Oracle vector port. No causal DB-only speed claim.',
 'scope':'Explicit fresh empty experiment runtime; no Oracle connection or writes, no migration, no product/pointer changes. Concurrent ADR1246 storage repair is separate.',
 'evaluation':'No evaluator model. Offline source equality, final saved/returned consistency, and question-part coverage review; no external legal-currentness certification.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='SQLite request completion, source integrity and saved answer consistency',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1245-experiment-v1/live'],'changes':'Historical Oracle failed run only; no new Oracle model calls','controls':'Not a same-condition DB A/B'}, {'id':'sqlite','role':'candidate','derived_from':['baseline'],'changes':criteria['differences'],'controls':criteria['controls']}]
m['runs'][0].update(arm_ids=['sqlite'],selection_rule=criteria['sample'],artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Known article369 question; selected local SQLite generation',version='MAIN128-20261030',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='No retrieval implementation modification or recall-effect comparison. One functional SQLite retry; original delivery measured, no golden recall claim.'
m['retrieval_accounting'].update(changed=False,corpus_total=1547,not_applicable_reason=reason,stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':None,'artifact_path':None,'sha256':None,'not_applicable_reason':reason})
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
snapshot=ac.snapshot(ADR,'sqlite',list(r['files']),experiment_id=m['experiment_id'],arm_id='sqlite',run_ids=['run-001'])
for n,h in r['files'].items():
 p=snapshot/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
ac.freeze(snapshot);assert not ac.validate(snapshot),ac.validate(snapshot)
c=read(snapshot/'candidate.json');v=c['revisions'][-1];b={'manifest_path':str((snapshot/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(snapshot/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(b,candidate_id='sqlite',experiment_id=m['experiment_id'],arm_id='sqlite',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))])
m['design']['execution_note']='Exact frozen snapshot equals selected MAIN128. Actual service imports verified selected release; research runner only records calls and injects explicit user authorization and common ExperimentClient transport. No product patch.'
put(ADR/'실험/manifest.json',m)
paths=[ROOT/'service.py',ROOT/'service/__init__.py',ROOT/'service/service.py',ROOT/'02_BACKEND/lawrag/research/experiment_client.py',ROOT/'02_BACKEND/lawrag/core/request_deadline.py',ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json',ROOT/'06_TOOLS/maintenance/experiment_json.py',ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json']
data=ROOT/r['data_path'];paths+=list(data.rglob('*.sqlite'))+list(data.rglob('*manifest*.json'))
inputs={str(p.relative_to(ROOT)):sha(p) for p in paths}
inputs.update({str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json')})
for p in T.glob('*.py'):ast.parse(p.read_text())
put(DES/'freeze.json',{'code_root':r['code_root'],'files':r['files'],'candidate_revision':b,'pointer_sha256':sha(pointer),'inputs':inputs,'scripts':{str((T/n).relative_to(ROOT)):sha(T/n) for n in ('live.py','common.py','cm_authorization.py','resource_guard.py')},'data_readonly':True,'oracle_access':False})
print('Frozen MAIN128/495 with SQLite source/state; same question once; ontologyOFF; source files',len(inputs))
