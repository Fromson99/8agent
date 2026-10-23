from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1010-delegated-definition-selection/artifacts'
m=read(ADR/'실험/manifest.json');parent=read(old.parent/'실험/manifest.json');s=read(old/'stage.json')
m['design'].update({k:v for k,v in parent['design'].items() if k not in ('arms','code_isolation')})
m['design'].update(hypothesis='A flat explicit necessity enum generated before its independently nullable executable step avoids action-branch grammar bias. Host validates NEEDS_SOURCE/action and RESOLVED/read-receipt consistency. Keep exact delegated definition cards and bounded termination; no target auto-selection or extra monitor call',primary_metric='Native necessary connected-original reachability and bounded termination; declared pending content versus actual source receipts.',success_criteria='Deterministic contracts pass for explicit model-owned status on actual wire, unavailable/irrelevant connections, unresolved delegated content, source authorization, replay, and explicit whole-article selection. One native known public request reads Act97 and the expense-detail paragraphs3/5 of Decree163, reaches final answer within14 physical calls, no source or ACL mismatch, no pending necessary original represented as sufficient. No forced article target, extra monitor call, adaptive rerun or fallback.',failure_criteria='Required connected content unread, premature sufficient termination, unnecessary repeated browsing without a material need, source/ACL/hash violation, repair exhaustion, or no answer in14calls.',sampling='One known exposed public question from completed ADR1005. Historical comparison descriptive only. Synthetic deterministic contracts test mechanics, not generalization.',execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'stage_probe_calls':0,'native_physical_call_ceiling':14,'max_calls_total':14,'native_profile_model_attempts':14,'max_transport_retries':0,'concurrency':1,'rss_ceiling_gib':6,'minimum_available_gib':3})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
m['design']['arms'][0].update(changes='Completed ADR1010 historical behavior',controls='No new baseline calls; current deterministic projection/request-entry fixes included in candidate and listed by hash')
m['design']['arms'][1].update(changes='Explicit necessity first in one flat clause-review schema; dependent action validation, same parent definition cards and14call budget',controls='Same public data/model, no article/query special case, no monitor LLM')
m['runs'][0].update(selection_rule=m['design']['sampling'],artifact_path=str((ART/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[{'role':'native-only','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
save(ADR/'실험/manifest.json',m);save(ART/'design-before-implementation.json',{'design':m['design'],'parent_freeze_sha256':sha(old/'design-freeze.json')})
files=list(read(old/'design-freeze.json')['files']['candidate'])
files += ['05_TESTS/CONTRACTS/'+n for n in ('test_bounded_delivered_handoff.py','test_navigation_delivery_recovery.py','test_focused_input_modality.py','test_investigation_completion_adr0678.py','test_nested_minimal_output.py')]
files=list(dict.fromkeys(files));files=[n for n in files if (ROOT/n).is_file()]
D=ac.snapshot(ADR,'candidate',files,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
# Start from current working code, then explicitly carry the completed parent's four isolated changes.
import shutil
P=ROOT/read(old/'stage.json')['roots']['candidate']
for n in ('answer_progress.py','decision_projection.py','connection_scope.py','law_candidates.py','delegated_content.py','content_plan.py','unit_relations.py','completion_execution.py'):
 shutil.copyfile(P/'02_BACKEND/semantic_runtime/legal_agent'/n,D/'snapshot/02_BACKEND/semantic_runtime/legal_agent'/n)
for n in ('test_source_content_completion.py','test_source_content_api.py','test_delegated_content.py','test_content_plan.py','test_content_plan_api.py','test_delegation_frontier.py'):
 shutil.copyfile(P/'05_TESTS/CONTRACTS'/n,D/'snapshot/05_TESTS/CONTRACTS'/n)
shutil.copyfile(old/'offline-required-content.json',ART/'offline-required-content.json')
save(ART/'stage.json',{'base_release':s['base_release'],'roots':{'baseline':s['roots']['baseline'],'candidate':str((D/'snapshot').relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'pointer_sha256':s['pointer_sha256'],'working_before':{n:sha(ROOT/n) for n in files},'parent_artifacts':str(old.relative_to(ROOT))})
shutil.copyfile(old/'known-request.json',ART/'known-request.json')
save(ART/'failure-contract.json',{'delivery_loss':{'class':'deterministic_consumer_bug','owner':'evidence_inventory / Investigation.result','repair':'merge exact confirmed delivered spans without adoption','model_calls':0,'final':'UNASSESSED original pack; explicit omissions at size limit'},'hidden_connection':{'class':'presentation_bug','owner':'connection_scope.offer_choices','repair':'bounded verified partial cards plus continuation menu, source witness and ACL rechecked','model_calls':0},'over_investigation':{'owner':'existing request budget and answer_progress','limits':{'model_attempts_total':14,'finalization_reserve':3,'no_change_steps':2,'schema_repair':1,'transport_retries':0},'final':'limited answer preserving verified originals and missing sources'},'fatal':['ACL','source hash','state binding'],'resume':'existing journal and request budget preserved; no reset'})
print('Snapshot',len(files),D)
