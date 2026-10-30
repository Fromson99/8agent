from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent
A=R/'04_EXPERIMENTS/ADR/ADR-1174-assessment-answer-consistency';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-1173-required-source-server-execution'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
criteria={'hypothesis':'Reject unscoped PARTIAL/INSUFFICIENT assessments in existing one-repair owner; keep material gaps in bounded investigation or limited answer; no free narrative generation for unresolved assessment; preserve normal covered answers and grounded exclusions.',
'checks':['Saved1173 CM001 exact assessment rejected for empty gaps before commit','Existing single ASSESS repair: correction accepted, repeated error stops without COMPOSE/unsafe publication','Valid required source reentry, fact request, normal answer and non-material exclusion remain allowed','Unresolved final assessment uses accepted claim text and explicit limitations; no composer model or premature streaming','Candidate130 inherited technical plus focused completion tests; regressions compared to same parent code','Live CM001 once, then007/009 once each only if integrity and consistency gate passes; no automatic repeat'],
'failure':'Preserve all failures; stop further live cases on same contradiction/failed validation/transport or incomplete storage. A valid limited answer may pass consistency but is not a complete legal answer. Do not infer legal correctness from HTTP200.',
'live':{'model':'qwen/qwen3.8-27b','cases':['cm-001','cm-007','cm-009'],'repeats':1,'max_physical_per_case':40,'max_tools':1024,'max_seconds':1800,'output_cap':None,'provider':'Chutes FP8, confirmed429 only request-lifetime switch Near AI FP8 once','stronger_model_comparison':False},
'resource':read(P/'artifacts/design/criteria.json')['resource'],
'failure_contract':{'input':'schema-valid ASSESS and committed ASSESS consumed by COMPOSE/API/storage','class':'DECISION_CONFLICT','owner':'completion_execution existing ASSESS loop, initial plus1 repair','correction':'No automatic legal meaning, gap kind/target/materiality or coverage upgrades. Model supplies explicit remaining need or evidence-grounded complete judgment. No fabricated law/article.','budget':'existing40/1024/1800 and reentry reserve unchanged','preservation':'raw outputs, DecisionJournal, accepted assessment, limits, code/data binding','terminal':'bounded source reentry, explicit limited answer or InvestigationPending on repeated invalid judgment'},
'authorization':'2026-10-28 user: 수정해보고 다시 테스트해봐. Previous gate failures remain immutable.',
'scope':'Isolated implementation and new test; MAIN112 remains until separate same-code integration/qualification.'}
put(D/'criteria.json',criteria)
for n in ('baseline.json','cases.json','corpus.json','authorization.json','provider-policy.json'):put(D/n,read(P/'artifacts/design'/n))
put(D/'parent-freeze.json',f);put(A/'artifacts/evaluation-only/cases.json',read(P/'artifacts/evaluation-only/cases.json'))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Assessment/answer consistency and source/storage integrity, not legal accuracy',success_criteria=criteria['checks'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'guarded','role':'candidate','derived_from':['ADR-1173-experiment-v1/executed'],'changes':criteria['hypothesis'],'controls':'Same MAIN112 data,1173 provider/source-first code,model,budgets'}],retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{'guarded':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}})
m['runs'][0].update(arm_ids=['guarded'],selection_rule='Stored CM001 output and synthetic fault contracts; CM001 once gates007/009 sequentially',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[];m['llm_policy']['provider_override']=read(P/'실험/manifest.json')['llm_policy']['provider_override'];m['llm_policy']['provider_override'].update(path=str((D/'provider-policy.json').relative_to(R)),sha256=sha(D/'provider-policy.json'))
m['dataset'].update(name='Known CM001 consistency failure and gated CM007/009',version='v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['retrieval_accounting'].update(changed=True,stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),'sha256':'PENDING'})
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'guarded',present,experiment_id=m['experiment_id'],arm_id='guarded',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h,n
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
for n in ('common.py','freeze.py','check.py','regression.py','test_supervisor.py','test_native_supervisor.py','test_supervisor_paging.py','test_source_goals.py','test_provider.py','test_serving_provider.py','api_fixture_integrated.py','live.py','resource_guard.py','cm_authorization.py','audit_result.py','audit_storage.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1173'/n).read_text().replace('ADR-1173-required-source-server-execution','ADR-1174-assessment-answer-consistency').replace("'executed'","'guarded'")
 (T/n).write_text(s)
print('Isolated parent463files; criteria frozen',S)
