from common import *
from copy import deepcopy
DES.mkdir(parents=True,exist_ok=True)
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1281-scenario-review-schema-live/artifacts/design'
for name in ('source.json','ontology-input.json','ontology-config.json'):put(DES/name,read(prior/name))
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');selected=read(ROOT/pointer['manifest_path'])
baseline=read(prior/'baseline.json');baseline.update(pointer=pointer,pointer_sha256=sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),selected_release=selected)
baseline['release']={**deepcopy(selected),'data_path':read(DES/'source.json')['data_path'],'data_manifest_sha256':sha(ROOT/read(DES/'source.json')['data_path']/'manifest.json')}
put(DES/'baseline.json',baseline)
cases=read(prior/'cases.json');case=cases[0]
case['request']['json'].update(session_id='adr1297-main134-display',request_id='adr1297-baseline')
case['followup_plan']=['new actual baseline cost1380000 approval unknown','one explicit rereview only if incomplete','numeric high1725000 low735000 rule2450000 with explicit cost binding','independent actual semantic low/high/rule from original baseline, each once','duplicate requests and reread original without additional model calls']
put(DES/'cases.json',cases)
criteria={'hypothesis':'Unchanged MAIN134 keeps current scenario prose separate from original case history and repairs exact offered computed-gap IDs in prose, while preserving source-bound claims, authoritative calculation and uncertainty in three Qwen branches.',
 'success':['Baseline and all three independent semantic branches adopt source-bound claims and preserve uncertainty',
 'Low735000: numeric condition TRUE; high1725000: FALSE; rule limit2450000 with cost1380000: TRUE; approval remains UNKNOWN and final permission UNCONFIRMED',
 'All scenario answers include host calculation/comparison receipt equal to independently recomputed approved plan, even if model review fails; this display alone is not a semantic pass',
 'Raw gap reasons contain no filler repeats or nonexistent numbered gaps; offered computed_gap_ref choices expand only explicitly selected missing FACT inputs',
 'Current limitations and need reasons do not repeat original cost1380000 as the current low/high issue; historical issue and declaration preserve original text in separately labelled fields',
 'If an exact offered computed_gap_ref appears in a rejected raw gap reason, preserve it and exercise the existing one repair; only accepted current prose must be free of those IDs',
 'No obsolete application_links/value-role/comparison_text or server condition_results authorship on actual new scenario wire; host execution catalog omitted and current inputs/results retained',
 'Exact repeated baseline question and first clause occur once in actual scenario input; lossless restore and single full base prompt',
 'Current model prose does not reuse superseded amount/threshold; honest historical comparison rejection recorded as a failure, not repaired by slicing',
 'Numeric actions0 model calls; all duplicate requests0 calls; original case preserved',
 'Code/inputs/source/ACL/wire exact; physical/reserved budgets match, UNKNOWN0, no resource stop'],
 'failure':'Source-only fallback remains safe but is semantic failure. No response injection, product edits or terminal cell retries. Existing policy permits confirmed429 provider switching; UNKNOWN or unresolved provider failure stops subsequent model turns.',
 'limits':{'physical_model_calls_total':20,'per_turn_wall_seconds':1800,'per_model_seconds':180,'rss_GiB':4,'minimum_start_available_GiB':5,'minimum_available_GiB':3,'max_swap_growth_MiB':128,'minimum_workspace_free_GiB':20},
 'observer_revision':'Append-only started/finished files; calls summary written once. ADR1295 full HTTP200 response preserved separately from product UNKNOWN caused by observer exception; never reopen old request or journal.',
 'virtual_address_limit':'No RLIMIT_AS; actual RSS4GiB and available RAM/swap/disk watchdogs retained. Python/native mmap virtual reservation is not actual RSS. One experiment at a time.',
 'quality':'Known synthetic regulation/amounts, probe in_sample. Manual inspection against frozen rules, no external judge. ADR1286 is historical context only, not a paired causal A/B or legal-quality/generalization claim.',
 'fixed_scope':'No new evaluation specification/approval/publication. Existing N1 unregistered effect remains UNKNOWN. Actual code is exactly completed ADR1292 and current MAIN134 serving subset; MAIN134 remains selected. Native API and UI-facing projection are exercised; no actual browser or GENOS deployment claim.'}
put(DES/'criteria.json',criteria)
put(DES/'authorization.json',{'user_instruction':'한번실험해봐','external_transmission_allowed':True,'scope':'Same synthetic regulation and server-issued actions, new baseline plus three independent scenarios','document_ids':['synthetic-whatif-v1'],'questions':[case['request']['json']['question']],'model':'qwen/qwen3.8-27b','maximum_model_turns':5,'physical_limit':20})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source-bound semantic answers in all3 branches with correct current values, uncertainty and no filler gaps',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed ADR1292 MAIN134 local contracts and synthetic Oracle connectivity; no actual model claim',controls='Historical ADR1290 actual1of3, exact ID leaked and high UNKNOWN; no causal quality comparison')
m['design']['arms'][1].update(changes='Unchanged MAIN134 current/history display isolation and exact offered ID repair, new actual Qwen calls',controls='Same originals/approved ontology/amounts/current policy; fresh isolated runtime')
m['runs'][0].update(arm_ids=['verified'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='One prospective conversation, three independent branches; no terminal repeats')
m['dataset'].update(name='Synthetic MAIN134 current/history display and three-scenario live probe',version='20261103-v1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='Fixed retrieval/source path, scenario-only behavioral probe; no retrieval effectiveness comparison'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1292-rag-ontology-console-integration/artifacts/design/freeze.json')
assert pointer['generation']==134, pointer['generation']
sources=set(parent['files']);assert all(sha(ROOT/n)==h for n,h in parent['files'].items())
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=ac.snapshot(ADR,'verified',sorted(sources),experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'])/'snapshot'
put(DES/'working-before.json',{n:sha(ROOT/n) for n in sorted(sources)});put(DES/'candidate-path.json',{'snapshot':str(S.relative_to(ROOT))})
put(DES/'parent-working-equality.json',{'files':len(sources),'same_as_completed1292':True,'main134_unchanged':True,'new_product_changes':0})
print('Prepared unchanged',len(sources),'files')
