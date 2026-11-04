from common import *
DES.mkdir(exist_ok=False)
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path'])
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1342-target-connection-completion-review/artifacts/design/candidate-checked.json')
files=list(parent['selected_files']);before={n:sha(ROOT/n) for n in files}
assert pointer['generation']==142
put(DES/'baseline.json',{'pointer':pointer,'release':release})
put(DES/'working-before.json',before)
put(DES/'prior-working-delta.json',{'changes_since1342':[n for n,h in before.items() if parent['selected_files'][n]!=h]})
criteria={
 'hypothesis':'Typed model-owned workspace edits and exact source-reference expansion prevent malformed proposals; original acquired read history must remain visible to source-goal accounting when ontology own-block reads replace the current selection.',
 'success':['C1 explicit ASCII local handles and operation-specific schemas, precise shown origin/source references; no invented statement, source or approval.',
 'C2 model creates source-grounded statements through existing proposal/apply/compile path; navigation-only edits and existing stored canonical operations remain compatible.',
 'C3 source goals account for exact verified historical material of the same branch/offer; full vs partial/heading, wrong scope/version/document, tampering and excluded needs stay distinct.',
 'C4 proposal repair owns one correction, original failures persist, duplicate/resume add no calls, unknown is not resent.',
 'C5 new immutable compressed observer versions preserve both known responses and aggregate usage without overwriting any old experiment.',
 'C6 new contracts, existing related regressions, actual mock API and code pins pass before selective working integration; exact528 bytes and prior changes preserved.'],
 'failure':['No removed source/ACL/hash/adoption validation, no automatic legal sufficiency, no article-specific branch or new retries, no active MAIN/data/publication changes.'],
 'failure_contract':{'owner':'Workspace._job owns one model repair; Workspace.apply owns exact canonical validation/commit. source_goal_control.refresh owns factual acquired coverage, final ASSESS still owns semantic review.',
 'allowed':'Source identity and quote offsets reconstructed only from explicit model source/quote/occurrence; saved exact history counted as original acquisition, never legal adoption.',
 'budget':'Existing per-job 2 attempts/360s, per-call180s, normal RAG40 and all checkpoint/replay limits retained.',
 'end':'Uncorrected proposals remain INVALID, unknown stays UNKNOWN, partial evidence remains partial, no source-only outcome counted as complete.'},
 'limits':{'new_model_calls':0,'heavy_workers':1,'rss_GiB':5,'available_start_GiB':5,'available_stop_GiB':3,'swap_growth_MiB':128},
 'scope':'Technical repair and working integration; real Qwen after final freeze in separately reserved followup. No MAIN promotion.'}
put(DES/'criteria.json',criteria)
cases=[{'id':'authoring-contract','scope':'typed edits, explicit source references, exact quote occurrences, one repair, no mutation before apply, compilation consumer'},
 {'id':'review-target-contract','scope':'same-branch history from actual ontology reads, exact goal coordinates and complete source verification, final scope review unchanged'},
 {'id':'observer-repair','scope':'immutable raw capture and monotonic usage snapshots on successive known responses'}]
put(DES/'cases.json',cases)
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Checklist contracts pass without source/state or semantic validation regressions',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Current working528 including1342, frozen before edits',controls='No new baseline LLM')
m['design']['arms'][1].update(changes='Typed authoring proposal with exact canonical reconstruction, historical acquisition accounting, new observer recording',controls='Original semantics, validators, rights, budgets, MAIN142 preserved')
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Prospective synthetic contracts, saved1343/1345 failure evidence and mock actual API; no new model',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Ontology authoring and source-goal history repair contracts',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[]
for x in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):x['not_applicable_reason']='Deterministic contract/receipt checks; no retrieval membership or performance comparison'
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'repaired',files,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
products=['02_BACKEND/semantic_runtime/ontology_work/wiki_contracts.py','02_BACKEND/semantic_runtime/ontology_work/wiki_workspace.py','02_BACKEND/semantic_runtime/legal_agent/source_goal_control.py']
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':products})
print(can/'snapshot')
