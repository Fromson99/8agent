from common import *

DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/pointer['manifest_path'])
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1341-page-cycle-charter-live/artifacts/design/candidate-bounded.json')
files=list(parent['selected_files']);before={n:sha(ROOT/n) for n in files}
assert before==parent['selected_files'] and pointer['generation']==142
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'working-before.json',before)
criteria={
 'hypothesis':'Per-original connection inspection must reach the existing termination supervisor; applying a general rule requires checking the requested action and exceptions. Claim-specific adoption diagnostics and safe incomplete publication preserve strict validation.',
 'success':[
 'C1: An inspected unrelated source cannot bypass termination supervision for uninspected answer basis; exact scope spans, legacy input, resume and bounded unavailable paths retained.',
 'C2: The same applicability and incomplete-scope guidance reaches primary selection, supervisor and final assessment; no article/answer constants or forced traversal of all links.',
 'C3: SCOPE_CLAIM_EVIDENCE reports exact failed claim, cited vs adopted evidence and relevant judgment links; model chooses adoption, revision or unresolved outcome; validator unchanged.',
 'C4: One existing repair attempt only; correction can succeed, repeated failure preserves originals and incomplete state, UNKNOWN/budget/replay protections retained.',
 'C5: Incomplete judgments/conflicts remain in internal receipts but their unvalidated legal conclusions are absent from public limitations.',
 'C6: New contracts plus relevant regressions and actual mock API pass, changed-source SQL plans remain executable-identical, same candidate/working528 hashes and engine pins verified.'],
 'failure':['No automated legal conclusion, evidence adoption, target article hardcoding, weakened source/ACL/hash validation, new retries or MAIN change.'],
 'failure_contract':{'owner':'connection_scope projects inspected scope; existing investigation_supervisor owns termination review; completion_execution owns one repair; read_judgment_final owns public incomplete limitations',
 'allowed_change':'Exact inspection facts, guidance and diagnostic/public projection only; semantic choices remain model proposals with original validators',
 'budget':'Existing40 calls, final reserve3, supervisor2, assessment repair1, original deadline and page-cycle guard unchanged',
 'termination':'Existing bounded handoff and source-only fallback; incomplete source is never absence or successful legal answer'},
 'limits':{'model_calls':0,'heavy_workers':1,'rss_GiB':5,'swap_growth_MiB':128,'available_start_GiB':5,'available_stop_GiB':3},
 'scope':'User-requested working fix. Deterministic tests and recorded1341 reproduction here; live validation in separate child after freeze/integration. MAIN142 unchanged.'}
put(DES/'criteria.json',criteria)
cases=[{'id':'termination','scope':'Unrelated vs same inspected source, exact spans, narrowing, unavailable, legacy, resume and supervisor API'}, {'id':'assessment','scope':'Exact failed1341 explanation claim and successful/repeated repair'}, {'id':'display','scope':'Incomplete receipt remains auditable; public answer has originals and nonsemantic status only'}]
put(DES/'cases.json',cases)
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='All checklist contracts pass without weakening legal/source validation',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1341 exact528 working source',controls='No new baseline live calls')
m['design']['arms'][1].update(changes='Per-original connection finish supervision, applicability guidance, exact claim-adoption repair and incomplete public text',controls='Original schemas/validators, scope, budget and page-cycle guard retained')
m['runs'][0].update(arm_ids=['checked'],selection_rule='Prospective deterministic contracts and existing regressions, actual mock API, recorded1341 evidence; no live model here',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Source-specific termination and final review contracts with1341 failure evidence',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[]
for n in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):n['not_applicable_reason']='Control/diagnostic/display contracts; candidate membership and SQL unchanged, no corpus retrieval comparison'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'checked',files,experiment_id=m['experiment_id'],arm_id='checked',run_ids=['run-001'])
products=['connection_scope','answer_progress','investigation_supervisor','read_judgment_final','completion_execution']
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in products]})
print(can/'snapshot')
