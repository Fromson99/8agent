from common import *
from copy import deepcopy
DES.mkdir(parents=True,exist_ok=True)
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1281-scenario-review-schema-live/artifacts/design'
for name in ('source.json','baseline.json','ontology-input.json','ontology-config.json'):
 put(DES/name,read(prior/name))
cases=read(prior/'cases.json');case=cases[0]
case['request']['json'].update(question=case['request']['json']['question'],session_id='adr1286-bound-facts',request_id='adr1286-baseline')
case['followup_plan']=['new actual baseline cost1380000 approval unknown','one explicit rereview only if incomplete','numeric high1725000 low735000 rule2450000 with explicit cost binding','independent actual semantic low/high/rule branches from original baseline','duplicate each request and reread original']
put(DES/'cases.json',cases)
criteria={'hypothesis':'ADR1285 scoped application links, host-owned empty claim rows, separate full comparison prose and structured task/facts support all three actual scenario branches with current values and no source loss.',
'success':['Actual baseline and each of three independent hypothetical answers have claims and are source-bound','Low735000: amount passes, approval remains unknown, overall permission unconfirmed','High1725000: amount fails, approval remains separately unknown','RULE limit2450000: baseline cost1380000 retained, amount passes, approval remains unknown and rule is explicitly hypothetical','Actual scenario wire has one exact copy of repeated baseline question/source, no condition_results field to author, and shared review link definitions',
'Nonadopting claim lists are host-owned; unchanged approval/exception explanations do not require scenario application links; current explanation does not reuse old threshold even with comparison refs',
'Numeric branch0 calls; exact current facts; no previous amount as current fact source; original case preserved','Replayed API request0 calls; no unknown/resource stop/hash/ACL/source/wire mismatch'],
'failure':'No model output injection. UNKNOWN/provider failure stops further model turns; terminal failed cells not retried. Source-only fallback is safe rejection but not semantic success.',
'limits':{'physical_model_calls_total':20,'per_turn_wall_seconds':1800,'per_model_seconds':180,'rss_GiB':4,'minimum_available_GiB':3,'max_swap_growth_MiB':128},
'quality':'In-sample repaired workflow, same fixed amounts and same synthetic rule; no legal-quality generalization or stochastic A/B claim. Predefined source-bound ontology reused unchanged, not model authoring.',
'wire_audit':['Measure exact sent schema and system/user sizes; report structural branch counts separately from instance requirements','Check host-known constants, scenario condition copying, literal repetition requirements, canonical repeated subtrees and actual system exact repetitions','Review evidence-backed redundancy versus necessary source/claim/need accounting; no inferred token savings or causal quality claim']}
put(DES/'criteria.json',criteria)
put(DES/'authorization.json',{'user_instruction':'실험','external_transmission_allowed':True,'scope':'Synthetic regulation and exact server actions, three independently changed scenarios','document_ids':['synthetic-whatif-v1'],'questions':[case['request']['json']['question']],'model':'qwen/qwen3.8-27b','maximum_model_turns':5,'physical_limit':20})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual changed-value adoption and unknown approval preservation',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed ADR1285 contract/native fixture checks; historical ADR1284 actual0of3',controls='Historical only; no paired stochastic score')
m['design']['arms'][1].update(changes='Unchanged integrated ADR1285 scoped application/shared-review versions and structured scenario question; exact candidate equality required',controls='Same synthetic originals/approved ontology/model policy; new runtime, same fixed amounts')
m['runs'][0].update(arm_ids=['verified'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='One prospective conversation, three independent branches, no terminal reruns')
m['dataset'].update(name='Same synthetic scenario after lossless and shared contract fixes',version='20261102-r4',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='Fixed retrieval reused, functional scenario test; no retrieval effectiveness comparison';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
r=read(DES/'baseline.json')['selected_release'];sources=set(r['files'])
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):sources.add(str(p.relative_to(ROOT)));sources.update(read(p).get('files',{}))
sources.update(['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py'])
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=ac.snapshot(ADR,'verified',sorted(sources),experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'])/'snapshot'
put(DES/'working-before.json',{n:sha(ROOT/n) for n in sorted(sources)});put(DES/'candidate-path.json',{'snapshot':str(S.relative_to(ROOT))})
prior_fix=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1285-scenario-review-scope-contract/artifacts/design/freeze.json')
assert set(prior_fix['files'])==sources
assert all(sha(ROOT/n)==h for n,h in prior_fix['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'baseline.json')['pointer_sha256']
put(DES/'parent-working-equality.json',{'files':len(sources),'same_as_completed1285':True,'main_unchanged':True})
print('Prepared',len(sources))
