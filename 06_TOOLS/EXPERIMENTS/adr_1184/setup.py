from common import *
import shutil
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract'
f=read(P/'artifacts/design/execution-binding-002.json'); m=read(ADR/'실험/manifest.json'); T=Path(__file__).parent
criteria={'hypothesis':'An absolute monotonic deadline bounds each physical HTTP request including continuous partial traffic; a request-lifetime worker is killed and reaped at expiry. Unknown outcomes neither retry nor switch provider nor become accepted results.',
 'checks':['Real sockets: normal/error/429, stalled headers/body, continuous whitespace, slow completed response, expired before send, worker cleanup and no secret logs',
 'Serving gateway and common experiment client use the same deadline primitive; stage remaining time includes preparation and provider switch, every sent request remains charged',
 'Native API timeout is saved as UNKNOWN with partial receive diagnostics and returns without hanging; no late success or automatic retry',
 'Parent source-goal, ACL, original and provider contracts remain intact; paired regression has no new failures',
 'Actual CM007 exactly once after offline pass, CM009 once only if original/answer/storage/audit gates all pass'],
 'failure':'Timeout overrun beyond bounded cleanup tolerance, leaked worker, late accepted result, source/ACL mismatch, false completion, budget discrepancy or new regression blocks followup.',
 'deadline_seconds':180,'cleanup_tolerance_seconds':1.5,'per_case_budget':{'physical':40,'tools':1024,'seconds':1800,'output_cap':None},
 'live_order':['cm-007','cm-009 only after cm-007 passes'],'scope':'Isolated candidate; MAIN112 and GENOS unchanged; no stronger model or same-case automatic rerun',
 'diagnostic_limit':'Old call003 captured no response headers or chunks; upstream reason cannot be established retrospectively. Local cancellation does not prove remote cancellation.'}
put(DES/'criteria.json',criteria)
for n in ['baseline.json','cases.json','corpus.json','authorization.json','provider-policy.json']:
 put(DES/n,read(P/'artifacts/design'/n))
put(DES/'parent-freeze.json',f)
put(DES/'user-authorization.json',{'request':'3번째 호출에서 왜 멈췄는지 확인하고, 기한 넘겨도 안 끊기는 문제도 고쳐봐. 그다음 7번 다시 돌리고 통과하면 9번도 돌려.','session':'01a18102-29c3-78b3-9b53-cc33aaca63e7'})
for p in (P/'artifacts/evaluation-only').glob('*.json'):put(ART/'evaluation-only'/p.name,read(p))
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'bounded',[n for n in f['files'] if (ROOT/n).exists()],experiment_id=m['experiment_id'],arm_id='bounded',run_ids=['run-001']); S=C/'snapshot'
known={x['target_path'] for x in read(C/'candidate.json')['files']}
for n,h in f['files'].items():
 assert sha(ROOT/f['code_root']/n)==h,n
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f['code_root']/n,S/n)
 if n not in known:ac.register_file(C,n,upstream_state='absent')
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1179').glob('*.py'):
 if p.name in ('setup.py','common.py','document_result.py','summarize.py','summarize_interrupted.py','audit_interrupted.py','repair_checks.py'):continue
 (T/p.name).write_text(p.read_text().replace('ADR-1179-source-scope-completion-contract','ADR-1184-model-absolute-deadline').replace('ADR-1179','ADR-1184').replace('adr_1179','adr_1184').replace("'scoped'","'bounded'"))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Absolute call deadline and audited native case completion',success_criteria=criteria['checks'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'bounded','role':'candidate','derived_from':['ADR-1179-experiment-v1/scoped'],'changes':'Absolute external transport deadline and receive diagnostics','controls':'Same model, source goals, data, scope and budgets'}]);m['runs'][0].update(arm_ids=['bounded'],selection_rule='Offline faults then CM007 once; CM009 only if007 passes',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='CM007/009 and transport deadline fault injection',version='v1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None,stage_ledger={'mode':'recorded','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((RUN/'retrieval-ledger.json').relative_to(ROOT)),'sha256':'PENDING','not_applicable_reason':None})
m['design']['retrieval_stage_plan']['stages_by_arm']={'bounded':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
put(ADR/'실험/manifest.json',m)
print('1184 criteria frozen; parent465 isolated')
