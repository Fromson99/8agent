from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/p['manifest_path']);B=ROOT/r['code_root']
assert p['generation']==100
assert all(sha(B/n)==h for n,h in r['files'].items())
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis='Source-bound prior answer scope reaches next tool selection; explicit requested uncertainty and consequence in existing assessment/action reasons reduce irrelevant expansion without suppressing necessary dependencies or adding model calls.',primary_metric='Paired frozen need/action correctness, verified known-query explanation, model calls and latency',success_criteria='Known candidate delivers source-bound article434 thresholds without unrelated company-type expansion and uses no more calls than paired MAIN100. Eight synthetic pairs: candidate >=7/8, no loss of necessary dependency/required comparison cases. No source/ACL/hash/state/contract regression. Latency reported, not guaranteed by a single pair.',failure_criteria='Any integrity regression, candidate <7/8, loss of necessary expansion, or known-question unsupported/missing answer rejects adoption. Preserve failed and partial calls. No adaptive retry.',criteria_frozen_before_run=True,sampling='Known question is in-sample. Eight newly authored synthetic fixtures are development probes, not legal generalization. Four ASSESS and four executable navigation decisions per arm.',execution={'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,'max_calls_total':96,'max_calls_per_service':40,'synthetic_calls':16,'sequential':True,'minimum_available_gib':3,'rss_ceiling_gib':6,'scope':'single request; no multiturn changes'},failure_recovery={'owner':'Existing output.bounded_decision navigation repair and ASSESS one-repair owner; gateway alone owns transport policy. Synthetic probes one physical call, no repair.','budgets':'Native profile deadlines and persisted counters unchanged; no new review call or new retry layer.','source_state':'Only currently presented exact source spans can rebind a prior opinion; no opinion can create a source, gap resolution or accepted legal answer. Hash corruption fails before model.','final_state':'Existing ANSWER/LIMITED_ANSWER/PENDING and source integrity validation; no forced finish or semantic heuristic.','consumers':'Existing decision payload, execution journal, assessment and native service output; no canonical API schema change.'})
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
for a in m['design']['arms']:
 a.update(changes='Exact selected MAIN100' if a['id']=='baseline' else 'Source-bound previous assessment context in tool choice; requested-uncertainty/counterfactual guidance in existing reasons',controls='Same code outside three files, public source generation, model, budgets, tool menu and source validators')
save(ADR/'실험/manifest.json',m)
tests=['05_TESTS/CONTRACTS/'+n for n in ('test_assessment_review_continuity.py','test_read_choice_input_preservation.py','test_source_span_norm.py','test_assessment_source_reply.py','test_bounded_delivered_handoff.py')]
D=ac.snapshot(ADR,'candidate',list(r['files'])+tests,experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);C=D/'snapshot'
drift=[]
for n,h in r['files'].items():
 if sha(ROOT/n)!=h:drift.append(n)
 shutil.copyfile(B/n,C/n)
save(ART/'stage.json',{'base_pointer':p,'base_release':r,'roots':{'baseline':str(B.relative_to(ROOT)),'candidate':str(C.relative_to(ROOT))},'candidate_dir':str(D.relative_to(ROOT)),'preexisting_working_drift':drift,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
print('Isolated',len(r['files']),'files; existing drift preserved:',len(drift))
