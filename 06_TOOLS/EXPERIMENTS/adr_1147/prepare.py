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
case={'id':'privacy-controller-source-001','source':{'type':'prospectively-authored-public-question','legal_quality_holdout_certified':False},'request':{'API_TYPE':'rag','json':{'question':'개인정보 보호법 제2조 제5호의 개인정보처리자는 누구를 뜻하나요? 해당 원문을 인용해 설명해 주세요.','document_ids':['ab58f0d6419c6868'],'public_question':True,'use_llm':True}}}
put(DES/'case.json',case);put(DES/'cases.json',[{'id':case['id'],'question':case['request']['json']['question']}])
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'authorization.json',{'user_request':'그럼 두 문제부터 수정하고, 미반영된 것들도 통합 검증해서 MAIN에 반영해. 실제 서비스에서 원문 조사부터 최종 답변까지 되는지도 확인해.','scope':'Selected MAIN109 actual service public question once; no answer key or gold sent','max_model_calls':40,'retries':'Native bounded recovery only, no whole-case retry'})
criteria={'hypothesis':'Qualified MAIN109 actual service can determine exact body scope, read original source, and publish actual grounded claims in its final answer.','success':['Exact selected MAIN109440files/profile/data and service.service with no app injection','HTTP200 with actual final claims and nonempty answer, not CLARIFY or excerpt-only','At least one actual original read; delivered spans and final quote match selected stored source; no ACL violation','No output cap fields, provider or model fallback, accepted malformed review, stale binding or fabricated claim references'],
'failure':'Any integrity/resource failure, timeout, HTTP failure, CLARIFY, no actual claims or no original read fails end-to-end criterion. Preserve all outcomes without re-running this case.',
'quality':'Operational single public question; no legal quality, holdout effect or broad speed certification',
'limits':{'questions':1,'attempts_per_case':40,'tools_per_case':1024,'wall_seconds_per_case':1800,'concurrency':1,'rss_gib':4,'as_gib':6,'minimum_available_gib':3,'minimum_disk_gib':20,'swap_max_gib':0.5,'physical_call_watchdog_seconds':240,'minimum_provider_start_interval_seconds':65},
'watchdog':'Experiment-only unknown outcome guard; uses lesser of240seconds and remaining request budget. Writes partial records and terminates this process without retry or asserting upstream cancellation. Product timeouts unchanged.',
'model':'qwen/qwen3.8-27b, Parasail FP8 only, reasoning none, no fallback, no output token cap',
'latency':'Full request wall minus sequential model transport minus observed glossary loads, plus reported application setup. Include screens, recovery, persistence; provider pacing reported separately; no1s achievement assumed.',
'runtime':'Actual selected service.service, ExperimentClient transport audit only. No injected product app, no prompt edits.'}
put(DES/'criteria.json',criteria)
paths=list(release['files'])+['02_BACKEND/lawrag/research/experiment_client.py']
candidate=ac.snapshot(ADR,'selected',paths,experiment_id='ADR-1147-experiment-v1',arm_id='selected',run_ids=['run-001'])
for n in release['files']:(candidate/'snapshot'/n).write_bytes((code/n).read_bytes())
ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('live.py');m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual original read, final claims+answer, exact source and service binding',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,
 arms=[{'id':'selected','role':'candidate','derived_from':['ADR-1146-experiment-v1/integrated'],'changes':'No product changes; observe qualified selected MAIN109 once','controls':'Exact selected440files/data/profile/model/budgets; public question, no answer key'}],
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{'selected':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'selected','arm_id':'selected','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
m['dataset'].update(name='Single public controller definition on selected MAIN109',version='privacy-controller-source-001 /20261027',frozen_source=str((DES/'case.json').relative_to(ROOT)),sha256=sha(DES/'case.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['runs'][0].update(arm_ids=['selected'],purpose='primary',selection_rule='One predeclared public question on actual selected MAIN109, no whole-case retry',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Unchanged selected source retrieval; operational original/cited identities measured after model selection')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
freeze={'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release_manifest_sha256':pointer['release_manifest_sha256'],'code_root':release['code_root'],'files':release['files'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in sorted(DES.glob('*.json'))},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py'),'candidate_manifest_sha256':sha(candidate/'candidate.json'),'model_calls':0}
freeze['inputs']['02_BACKEND/lawrag/research/experiment_client.py']=freeze['client_sha256']
put(DES/'freeze.json',freeze)
print('Frozen selected MAIN109440files and one public question; no model calls')
