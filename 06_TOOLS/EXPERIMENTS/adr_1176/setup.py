from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1176-response-contract-route-recovery';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-1175-source-goal-scope-contract';L=R/'04_EXPERIMENTS/ADR/ADR-1174-assessment-answer-consistency'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
criteria={'hypothesis':'Branch-specific typed response errors use existing same-view one-repair owner before effects; invalid input does not consume source routes; exact-source preselection returns to bounded alternative selection without losing goals or halt cause.',
'checks':['Typed field paths, submitted values and allowed choices for JSON/required/type/enum/unknown IDs/action conflicts; no invalid effects','Same frozen view/schema and single durable repair across rejection and resume; normal path no extra calls','Required source preselection with consumed exact route returns to model recovery; distinct intermediate routes bounded and goals preserved','Exact handoff cause retained through SELECT/ASSESS/API instead of generic no progress','Existing177 contracts plus fault/native API contracts; no new same-parent regressions','Saved CM001 rejection and CM009 malformed input/native route replay before live','CM001 once then007/009 sequential only if preceding content/integrity gate passes; failed case never rerun'],
'failure':'Invalid tool execution, lost goal/source/ACL, nested repair/budget reset, premature source-route handoff, contradictory or incomplete answer fails; stop subsequent live cases on failure. No legal quality certification.',
'live':{'model':'qwen/qwen3.8-27b','cases':['cm-001','cm-007','cm-009'],'repeats':1,'max_physical_per_case':40,'max_tools':1024,'max_seconds':1800,'output_cap':None,'provider':'Chutes FP8, confirmed429 only Near AI FP8 once; same physical budget'},
'resource':read(L/'artifacts/design/criteria.json')['resource'],
'failure_contract':{'owner':'existing read-choice/ASSESS correction owners; gateway transport only','correction':'no guessed IDs/scopes/coordinates/claims; same current allowed menu; initial plus1 repair','terminal':'bounded route choice then explicit limited/pending if exhausted; preserve exact reason and independent validated reads','state':'DecisionJournal/CorrectionBudget/source goals and route receipts retained; rejection has no tool or no-progress effect'},
'authorization':'User 2026-10-28 한번전체 고쳐봐; follows requested fix and retest. Approved CM export authorization preserved.',
'scope':'isolated implementation and sequential retest first; working integration and MAIN only after same-code qualification; no GENOS/Git/email.'}
put(D/'criteria.json',criteria)
for n in ('baseline.json','cases.json','corpus.json','authorization.json','provider-policy.json'):put(D/n,read(P/'artifacts/design'/n))
put(D/'parent-freeze.json',f);put(A/'artifacts/evaluation-only/cases.json',read(L/'artifacts/evaluation-only/cases.json'))
put(D/'design-plan.json',{'path':'07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MODEL_RESPONSE_CONTRACT_REPAIR_PLAN_20261028.txt','sha256':sha(R/'07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/MODEL_RESPONSE_CONTRACT_REPAIR_PLAN_20261028.txt')})
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Validated response repair and continued source investigation without invalid effects',success_criteria=criteria['checks'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'repaired','role':'candidate','derived_from':['ADR-1175-experiment-v1/scoped'],'changes':criteria['hypothesis'],'controls':'Same464files/data/model/budgets; same original source scope'}],retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{'repaired':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}})
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Frozen fault/replay contracts then CM001 gates007/009 once each',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[];m['llm_policy']['provider_override']=read(L/'실험/manifest.json')['llm_policy']['provider_override'];m['llm_policy']['provider_override'].update(path=str((D/'provider-policy.json').relative_to(R)),sha256=sha(D/'provider-policy.json'))
m['dataset'].update(name='Known CM regressions plus frozen deterministic response/route contracts',version='v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['retrieval_accounting'].update(changed=True,stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),'sha256':'PENDING'});put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'repaired',present,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h,n
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1175').glob('*.py'):
 if p.name in ('setup.py','implement.py','finish.py','register_result.py'):continue
 (T/p.name).write_text(p.read_text().replace('ADR-1175-source-goal-scope-contract','ADR-1176-response-contract-route-recovery').replace("'scoped'","'repaired'"))
for n in ('live.py','resource_guard.py','cm_authorization.py','audit_result.py','audit_storage.py','replay_saved.py','regression.py','summarize.py','register_result.py'):
 (T/n).write_text((R/'06_TOOLS/EXPERIMENTS/adr_1174'/n).read_text().replace('ADR-1174-assessment-answer-consistency','ADR-1176-response-contract-route-recovery').replace("'guarded'","'repaired'"))
print('1176 criteria frozen; isolated',len(f['files']),'files')
