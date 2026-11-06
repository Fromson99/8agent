from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1398-lifecycle-alternate-providers/artifacts/design'
source=read(parent/'candidate-repaired.json');baseline=read(parent/'baseline.json');files=list(source['selected_files'])
put(DES/'baseline.json',baseline)
criteria={'authorization':'수정대상 수정하고 qwen으로 실험해봐','hypothesis':'Independent current-request relation and explicit post-command state verification catches unchanged-goal reentry on a changed purpose, repairs through the original model, and sends the repaired purpose to actual investigation.',
 'success':['Actual1398 rejected/false-pass proposals cannot execute when the reviewer identifies a changed current purpose; original LLM correction may change method, task, plan and scope without server semantic rewriting.','Same-goal followup must change effective task/issues; new topic must create a different goal;100-share condition must update facts without erasing prior context; review must target preceding accepted state.','Literal repeat preserves substantive answer with physical0; sameID adds0 sends. Native API durable events must match reviewed state; current source/ACL/wire/budget validation retained.','Optional authoring only after T1-T6 actual answers/review semantic gates pass; no HTTP200-only success. Build from immutable actual first judgment, explicit isolated original review, exact later claim use; downstream stages skipped if unmet.'],
 'failure':['One original proposal plus one bounded whole correction, unchanged ownership/budget/deadline. UNKNOWN quarantines that provider; other predeclared independent provider may run. No repeat of any old UNKNOWN. Resource stop aborts matrix.','No hardcoded legal answers/article choices, keyword-based relation inference, forced method/task rewriting, source validation removal or successful knowledge from failed requests.'],
 'limits':{'physical_total':80,'physical_per_native_request':40,'single_physical_seconds':180,'rss_gib':5,'available_ram_start_gib':5,'available_ram_floor_gib':3,'swap_growth_mib':1024,'heavy_workers':1},
 'providers':['reka','deepinfra'],'provider_precision':{'reka':'fp8','deepinfra':'bf16'},'single_repeat_each':True,'saved_prefix_responses_per_cell':5,'first_turn_is_not_fresh_provider_inference':True,'same_tested_1398_code_except_scoped_changes':True,'MAIN_change':False}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Correct current-request state transition and actual downstream question/issues, not HTTP200 or reviewer PASS alone',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis'];put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',files,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in files:shutil.copyfile(ROOT/source['code_root']/n,can/'snapshot'/n)
put(DES/'mutable-candidate.json',{'path':str(can.relative_to(ROOT)),'parent':source,'starting_working_hashes':{n:sha(ROOT/n) for n in files}})
print(can/'snapshot')
