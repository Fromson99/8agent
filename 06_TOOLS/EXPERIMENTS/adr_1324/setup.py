from common import *
import shutil
DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/pointer['manifest_path'])
assert pointer['generation']==140
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1322-multiturn-enum-diagnostics-working/artifacts/design/candidate-integrated.json')
files=list(release['files'])
before={n:sha(ROOT/n) for n in files}
assert [n for n in files if before[n]!=parent['selected_files'][n]]==['08_DEPLOYMENT/GENOS/start_sse.py','08_DEPLOYMENT/GENOS/stream_app.py']
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'working-before.json',before)
criteria={
 'hypothesis':'Model-authored review-link aliases lose branch cardinality in generation and add avoidable cross-reference failures. Direct claim/evidence fields preserve canonical constraints; the server can intern exactly equal relationships after shape validation without making legal choices. Scope USE/EXCLUDE/OPEN must expose their existing mechanical constraints during generation.',
 'success':['New generation asks for no review_links IDs/link_ref; canonical state, reason, claims, evidence and gaps are preserved exactly.','Empty-claim USE/CONDITIONAL, OPEN without gaps, EXCLUDE with claims are rejected by generation schema; valid combinations still pass original semantic checks.','v1/v2 saved receipts remain readable; v3 receipts bind every direct relationship and original proposal; repair uses the same direct format.','Actual service API synthetic first/repair/failure/duplicate path uses frozen candidate and correct final state; no extra physical calls or retry budget.','Prior completed1322 six fixes and1323 startup changes preserved; source/ACL/hash/UNKNOWN checks unchanged; native SQL semantics and selectedMAIN140 unchanged.'],
 'failure':['No legal status or claim inferred from shared evidence; no deletion of gaps to pass.','Any wrong source/evidence or tampered receipt must still fail.','No live model or service quality claim from synthetic tests.'],
 'limits':{'models':0,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128},
 'failure_contract':{'class':'generation/canonical shape mismatch and avoidable alias coupling','owner':'completion_execution existing first plus one repair; gateway repair remains disabled','correction':'Only exact relationship deduplication and server receipt IDs; original fields and legal judgments unchanged','terminal':'Existing source-only/incomplete or failure after exhausted repair; never automatic adoption','checks':'shape/semantic gap and source integrity, saved and repaired receipts, actual API and duplicate request'}}
put(DES/'criteria.json',criteria)
put(DES/'cases.json',[{'id':'direct-reference','scope':'Direct generation and exact server interning, no model-owned aliases'}, {'id':'scope-shape','scope':'All valid/invalid USE, EXCLUDE, OPEN field combinations'}, {'id':'saved-compatibility','scope':'v1/v2 readers and v3 tamper/repair/API consumers'}])
m=read(ADR/'실험/manifest.json')
m['integration'].update(result_arm='integrated',rationale='Preserve completed working1322 fixes and selected1323 startup while repairing final assessment generation contract',common_invariants=['Original text/ACL/hash/state/budget validation','No new models or selectedMAIN changes'],no_conflict_reason='Compared all525 working hashes: exactly two startup files differ from1322; they equal selectedMAIN140/1323. New work only touches assessment generation.',rollback_ref='ADR-1322-experiment-v1/integrated')
m['integration']['parent_contributions'][0].update(adopted='All six1322 product fixes and corresponding pins',excluded='No inherited live-answer success claim or MAIN139 pointer')
m['integration']['parent_contributions'][1].update(adopted='Two1323 startup import-order fixes and MAIN140 selected-release baseline',excluded='No new deployment or email; no inherited answer-quality claim')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact generation/canonical link preservation and failure contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1322 working + completed1323 startup, exact525 hash closure',controls='Same source/claims/gaps/budgets and old canonical validators')
m['design']['arms'][1].update(changes='Direct model claim/evidence relations with server-generated receipt and status-specific scope generation',controls='Same source/claims/gaps/budgets and canonical semantic validators')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Frozen new shape, receipt, API fault contracts plus prior relevant regression contracts; no adaptive model rerun',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Synthetic final-review contract and existing service API failure fixtures',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[]
for node in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):node['not_applicable_reason']='No corpus search or live model; synthetic generation/validation/record/API contracts only'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',files,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':['02_BACKEND/semantic_runtime/legal_agent/assessment_links.py','02_BACKEND/semantic_runtime/legal_agent/completion_execution.py','02_BACKEND/semantic_runtime/legal_agent/need_continuity.py'],'base_generation':140})
print(can/'snapshot')
