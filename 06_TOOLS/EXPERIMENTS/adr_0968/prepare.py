"""Freeze the selected MAIN and all registered CM51; never change serving code."""
from common import *
import sys,copy
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (DES/'freeze.json').exists()
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==98
release=read(ROOT/p['manifest_path']);assert sha(ROOT/p['manifest_path'])==p['release_manifest_sha256']
C=ROOT/release['code_root']
assert all(sha(C/n)==h and sha(ROOT/n)==h for n,h in release['files'].items())
registry=ROOT/'01_DATA/GOLDEN/registry-v2-risk_cm.json';raw=[x for x in read(registry)['cases'] if x['collection']=='cm']
assert len(raw)==51 and [x['id'] for x in raw]==[f'cm-{i:03d}' for i in range(1,52)]
cases=[{'id':x['id'],'question':x['question']} for x in raw]
put(DES/'cases.json',cases)
put(DES/'offline-reference.json',[{'id':x['id'],'question':x['question'],'reference_answer':x['reference_answer'],'as_of':x['as_of'],'targets':x['targets']} for x in raw])
put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release})
grant=read(C/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json');profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
put(DES/'authorization.json',{'user_request':'지금 메인으로 전체 cm 다 돌려봐','collection':'cm','question_count':51,'case_ids':[x['id'] for x in cases],'cases_sha256':sha(DES/'cases.json'),
 'scope':'Exact requested CM questions and selected public65 originals in current local MAIN; reference answers, target lists and annotations stay offline. No workflow/private source expansion.',
 'prior_scoped_request_context':'CM51 was separately user-authorized for earlier Qwen runs; this is a new execution under the present explicit all-CM request, not reuse of the old ADR-only authorization.',
 'original_export_metadata_preserved':True,'model':'qwen/qwen3.8-27b','provider':'OpenRouter / Parasail FP8'})
criteria={'hypothesis':'Unchanged MAIN98 can process every registered CM51 question through its actual local service and preserve auditable original sources, bounded recovery and final responses.',
 'success':['All51 questions attempted once in numeric order, failures retained, no adaptive whole-case retries','All physical product attempts recorded with exact request/response or explicit transport failure','No product code/profile/data/MAIN changes, selected418 files remain exact','Original spans and source scope checked separately from transport completion and reference coverage'],
 'failure':'Any code/data/state/authority mismatch stops new sending. Ordinary model/HTTP failures are recorded and next case continues. Budget is never reset for a started case.',
 'quality':'Collect answers and deterministic reference-version source coverage, without an external judge or a legal-accuracy certification. Registered reference coordinates may drift; report exact/version-matched status separately. No source coverage or HTTP200 is called a correct answer.',
 'limits':{'questions':51,'attempts_per_case':profile['max_model_attempts'],'wall_seconds_per_case':profile['wall_seconds'],'total_product_attempts':51*profile['max_model_attempts'],'concurrency':1,'rss_gib':6,'as_gib':8,'minimum_available_gib':3,'minimum_disk_gib':10},
 'runtime':'One serial process reuses read-only source/index resources. Every ordinary RAG request has fresh request state; no session/memory ID, no answer cache. Case-owned journals are recorded. No product app injection.',
 'resume':'Skip existing completed result. Mark a started case without result interrupted and preserve it; do not replay it. Continue only never-started cases under original run and remaining budget.',
 'model':'qwen/qwen3.8-27b; OpenRouter Parasail FP8; reasoning none; no provider/model fallback; ExperimentClient send_once instrumentation only',
 'baseline':'Single unchanged selected MAIN98 arm; known in-sample51, no paired comparison or MAIN promotion'}
put(DES/'criteria.json',criteria)
paths=list(release['files'])+['02_BACKEND/lawrag/research/experiment_client.py']
candidate=ac.snapshot(ADR,'observed',paths,experiment_id='ADR-0968-experiment-v1',arm_id='observed',run_ids=['run-001']);ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];runner=Path(__file__).with_name('live.py')
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='51 request outcomes, exact original/source verification, per-case calls/tokens/cost/latency and registered reference coverage; not certified legal accuracy',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,
 arms=[{'id':'observed','role':'candidate','derived_from':['ADR-0967-experiment-v1/integrated'],'changes':'None; byte-identical actual MAIN98 service with read-only instrumentation','controls':'Same selected data, native profile, Qwen policy and approved public65 scope; no answer targets/gold in product'}],
 retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{'observed':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{'candidate_id':'observed','arm_id':'observed','experiment_id':m['experiment_id'],'run_ids':['run-001'],'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner)}])
m['design']['execution']=criteria;m['dataset'].update(name='CM51 exact registered questions on MAIN98',version='registry-v2-risk_cm / collection cm / 20261021',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['runs'][0].update(arm_ids=['observed'],purpose='primary',selection_rule='All51 collection=cm in numeric order; once each. No risk_cm105, no selective rerun.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Selected retrieval unchanged. New original-read/final-citation measurements are post-selection; no retrieval-effect comparison.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
f={'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release_manifest_sha256':p['release_manifest_sha256'],'code_root':release['code_root'],'serving_files':release['files'],
 'files':{str(x.relative_to(ROOT)):sha(x) for x in sorted(DES.glob('*.json'))},'scripts':{str(x.relative_to(ROOT)):sha(x) for x in Path(__file__).parent.glob('*.py')},
 'client_sha256':sha(ROOT/'02_BACKEND/lawrag/research/experiment_client.py'),'candidate_manifest_sha256':sha(candidate/'candidate.json'),'product_model_calls':0}
put(DES/'freeze.json',f);print('Frozen51 exact questions and418 MAIN98 serving files; public65 scope; no model calls yet')
