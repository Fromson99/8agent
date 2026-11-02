from common import *
from copy import deepcopy
DES.mkdir(parents=True,exist_ok=True)
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==130
r=read(ROOT/p['manifest_path']);put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':r})
criteria={'hypothesis':'Working loop repairs preserve causes and bounded recovery for duplicate/conflicting source selection and malformed output; failed/UNKNOWN requests never silently redispatch.',
 'success':['All known remaining contract failures classified and repaired without loosening source/claim/ACL validation','Actual Qwen normal answer and each injected fault receives bounded recovery and validated saved answer','Same request returns saved answer or original controlled stop with zero extra model calls','Provider original and injected response preserved separately; no UNKNOWN retry, no 500/uncaught crash, physical budgets retained'],
 'limits':{'physical_model_calls_per_case':40,'tool_actions':1024,'wall_seconds':1800,'per_model_seconds':180,'rss_GiB':4,'available_GiB':3,'swap_growth_MiB':128},
 'failure':'Any 422 or unavailable final answer is not successful recovery. UNKNOWN/429 exhaustion preserved; remaining cells stop rather than blind provider retries. One dispatch per case. No data-dependent tuning of frozen cells.',
 'cases':['normal','duplicate-selection','conflicting-selection','malformed-json'],
 'injection':'First actual Qwen READ proposal only: duplicate first selection; or same selection with contradictory relation; or truncate serialized content. Preserve provider raw before perturbation. All corrective responses are actual Qwen. Unreached injection is NOT_TESTED.',
 'scope':'SQLite source/records, actual service API, one existing public law document; explicit external-data authorization. No MAIN promotion, Oracle/GENOS/NFS/DDL work.',
 'quality':'Known question plus controlled output faults, in-sample probe, not legal-quality or production certification.'}
put(DES/'criteria.json',criteria)
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1251-general-evidence-review/artifacts/design'
base=read(old/'cases.json')[0];cases=[]
for name in criteria['cases']:
 c=deepcopy(base);c['id']=name;c['fault']=name;c['request']['json'].update(session_id='adr1266-'+name,request_id='qwen-recovery-'+name);cases.append(c)
put(DES/'cases.json',cases);put(DES/'corpus.json',read(old/'corpus.json'))
put(DES/'authorization.json',{'user_instruction':'전체다 수정했냐? qwen으로 실험하고 (데이터 보내도 됨 외부로) 확인해봐','document_ids':base['request']['json']['document_ids'],'questions':[base['request']['json']['question']],'external_transmission_allowed':True,'model':'qwen/qwen3.8-27b','scope':'Four frozen native loop recovery cases, new isolated runtime each; actual Qwen corrections','actual_thread_id':'01a19992-930c-73c2-830b-199e61fc1869'})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Validated answer recovery per injected fault plus zero extra calls on repost',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Historical MAIN130 audit; no new baseline model calls',controls='Previous immutable results only; no causal performance comparison')
m['design']['arms'][1].update(changes='Current verified working loop repairs plus any diagnosed general contract fixes isolated before live freeze',controls='Same public source/question/model/profile, fresh runtime, single controlled response fault')
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Four named scenarios frozen before live observations, first qualifying READ only',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Existing public article369 one-document question',version='MAIN130 selected source/current candidate',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='Recovery verification, no retrieval effect comparison or recall estimate.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason,stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':None,'artifact_path':None,'sha256':None,'not_applicable_reason':reason})
put(ADR/'실험/manifest.json',m)
sources=set(r['files'])
for path in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
 sources.add(str(path.relative_to(ROOT)));sources.update(read(path).get('files',{}))
sources.update(['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py'])
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=ac.snapshot(ADR,'repaired',sorted(sources),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])/'snapshot'
put(DES/'working-before.json',{n:sha(ROOT/n) for n in sorted(sources)})
put(DES/'candidate-path.json',{'snapshot':str(S.relative_to(ROOT))})
print(S,len(sources))
