"""Freeze exact selected runtime and a prospectively authored public request."""
from common import *
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (DES/'freeze.json').exists()
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==109
release=read(ROOT/pointer['manifest_path']);code=ROOT/release['code_root']
assert sha(ROOT/pointer['manifest_path'])==pointer['release_manifest_sha256']
assert len(release['files'])==440 and all(sha(code/n)==h for n,h in release['files'].items())
registry_path=ROOT/'01_DATA/GOLDEN/registry-v2-risk_cm.json'
rows=[c for c in read(registry_path)['cases'] if c['collection']=='cm'];assert len(rows)==51
scope=sorted(read(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
cases=[{'id':c['id'],'request':{'API_TYPE':'RAG_ASK','json':{'question':c['question'],'document_ids':scope,'use_llm':True}}} for c in rows]
assert [c['id'] for c in cases]==['cm-%03d'%i for i in range(1,52)]
put(DES/'cases.json',cases);put(DES/'corpus.json',{'document_ids':scope,'selection':'Current MAIN109 approved public source scope; identical for51cases; not selected using gold targets','source_grant_sha256':sha(code/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')})
put(ART/'evaluation-only/cases.json',rows)
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'authorization.json',{'user_request':'일단 우리 cm 데이터 다 돌려봐봐 현재 메인기준으로 전부다 qwen으로 쏴도 됨 / 범위 확인: CM51문항','scope':'CM51 exact approved question bytes; currentMAIN109 approved public documents only; private CM origin is not relabelled public; no gold in product','max_model_calls':2040,'export_receipt':{'path':'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json','sha256':sha(ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json')},'case_question_sha256':{c['id']:__import__('hashlib').sha256(c['request']['json']['question'].encode()).hexdigest() for c in cases},'retries':'Native bounded recovery only, no whole-case retry'})
criteria={'hypothesis':'Observe every approved CM51 question through frozen current MAIN109/Qwen with complete answer/failure accounting; no product change or legal accuracy claim.','success':['Exact selected MAIN109440files/profile/data and service.service with no app injection','All51 dispatched once and accounted; per-case HTTP200+claims publication, limited answers, clarification and technical failures reported separately','For cases that read/cite originals verify exact source spans and ACL; no vacuous source-pass for no-read cases','No output cap fields, provider/model fallback, stale binding, or answer-key leakage; current MAIN remains unchanged'],
'failure':'Per-case HTTP/model/timeout/limited status is retained and next untouched case continues. Integrity, hash, ACL or resource faults stop batch. No same-case repeat. Parent supervisor enforces1860second process wall, >=existing1800request budget.',
'quality':'Operational single public question; no legal quality, holdout effect or broad speed certification',
'limits':{'questions':51,'attempts_per_case':40,'tools_per_case':1024,'wall_seconds_per_case':1800,'concurrency':1,'rss_gib':4,'as_gib':6,'minimum_available_gib':3,'minimum_disk_gib':20,'swap_max_gib':0.5,'physical_call_watchdog_seconds':240,'minimum_provider_start_interval_seconds':0},
'watchdog':'Experiment-only unknown outcome guard; uses lesser of240seconds and remaining request budget. Writes partial records and terminates this process without retry or asserting upstream cancellation. Product timeouts unchanged.',
'model':'qwen/qwen3.8-27b, Parasail FP8 only, reasoning none, no fallback, no output token cap',
'latency':'Full request wall minus sequential model transport minus observed glossary loads, plus reported application setup. Include screens, recovery, persistence; provider pacing reported separately; no1s achievement assumed.',
'runtime':'Actual selected service.service, ExperimentClient transport audit only. No injected product app, no prompt edits.'}
criteria['authorization_adapter']='Host-scoped exact CM question/current public source ACL; no public_question=true lie, no prior session history. Trusted authorization context only, product440files unchanged.'
criteria['evaluation']='Operational all-case collection. No LLM judge in this run; legal correctness not_scored. Reference answers kept physically separate for later review; no new accuracy claim.'
criteria['preflight']='First approved case executes to transport boundary with deliberate nonretryable synthetic stop,0externalcalls, separate artifacts. Full51run starts only if host grant works.'
put(DES/'criteria.json',criteria)
paths=list(release['files'])+['02_BACKEND/lawrag/research/experiment_client.py']
candidate=ac.snapshot(ADR,'selected',paths,experiment_id='ADR-1151-experiment-v1',arm_id='selected',run_ids=['run-001'])
for n in release['files']:(candidate/'snapshot'/n).write_bytes((code/n).read_bytes())
ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('live.py');m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual original read, final claims+answer, exact source and service binding',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,
 arms=[{'id':'selected','role':'candidate','derived_from':['ADR-1149-experiment-v1/selected'],'changes':'No product algorithm change;51CMquestions with exact host authorization adapter and audited transport','controls':'Exact selected440files/data/profile/model/budgets/current65source grant; approved CM questions, no gold'}],
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{'selected':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'selected','arm_id':'selected','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
m['dataset'].update(name='CM51 entire approved collection on selected MAIN109',version='cm-001..051 / registry-v2-risk_cm',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['runs'][0].update(arm_ids=['selected'],purpose='primary',selection_rule='All cm-001..051 once in ascending order, separate fresh process/runtime; ordinary failures continue, integrity/resource drift stops; no whole-case retry',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Unchanged selected source retrieval; operational original/cited identities measured after model selection')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
freeze={'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release_manifest_sha256':pointer['release_manifest_sha256'],'code_root':release['code_root'],'files':release['files'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in sorted(DES.glob('*.json'))},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py'),'candidate_manifest_sha256':sha(candidate/'candidate.json'),'model_calls':0}
freeze['inputs']['02_BACKEND/lawrag/research/experiment_client.py']=freeze['client_sha256']
for x in [registry_path,ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json']:freeze['inputs'][str(x.relative_to(ROOT))]=sha(x)
put(DES/'freeze.json',freeze)
print('Frozen selected MAIN109440files and CM51questions; no model calls')
