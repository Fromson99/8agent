from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1173-required-source-server-execution';D=A/'artifacts/design';T=Path(__file__).parent;P=R/'04_EXPERIMENTS/ADR/ADR-1171-source-goal-execution-model-probe'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json');assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
criteria={'hypothesis':'Execute already validated exact missing originals before model selection; reject invalid opinions independently; unify goal/gap closure; request-scoped gateway-only known429 provider switch.',
'checks':['Replay4 saved1172 outputs through actual choose_read and executor, distinguish reconstructed state','Verified EXACT goals execute existing authorized lookup/read before any selector model call','No rejected judgment adopted, independent original remains pending','Grounded exclusions/resolutions and real receipt coverage only; unresolved goals survive FINISH/ANSWERABLE','GoalID or authorized documentID plus coordinate; one server tool binding across normal/repair/pages','Gateway records2 physical attempts for429, only1 request-scoped switch; resume and budget binding','Retain77 parent plus25 provider contracts; no new relevant baseline regressions','CM001 once first; only on complete source-delivery-claim-answer-storage integrity and content gate then007/009 once each'],
'failure':'No adaptive live retries; same early termination/repeated failure stops followup cases. ACL/hash/stale/provider/model/unknown failures stop. Technical revisions preserve every failure. No semantic assertions from HTTP200.',
'live':{'model':'qwen/qwen3.8-27b','cases':['cm-001','cm-007','cm-009'],'repeats':1,'max_physical_per_case':40,'max_tools':1024,'max_seconds':1800,'finalization_model_reserve':3,'finalization_tool_reserve':4,'selection_time_reserve':30,'output_cap':None,'stronger_model_comparison':False},
'resource':{'workers':1,'min_available_gib':3,'max_rss_gib':4,'max_address_gib':6,'min_disk_gib':20,'swap_growth_mib':128},
'scope':'Candidate implementation then conditional same-code integration and MAIN/service verification; no GENOS field/email/git.',
'authorization':'2026-10-28 user: 이거 구현해봐 (quoted complete implementation/verification/conditional promotion plan).'}
put(D/'criteria.json',criteria)
for n in ('baseline.json','cases.json','corpus.json','authorization.json'):put(D/n,read(P/'artifacts/design'/n))
put(D/'provider-policy.json',read(R/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
put(A/'artifacts/evaluation-only/cases.json',read(P/'artifacts/evaluation-only/cases.json'))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Source-first execution and end-to-end validity; legal meaning scored separately',success_criteria=criteria['checks'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'executed','role':'candidate','derived_from':['ADR-1171-experiment-v1/controlled','ADR-1172-experiment-v1/switched'],'changes':criteria['hypothesis'],'controls':'Same MAIN112 data/model/budgets and known failures'}],retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}})
m['runs'][0].update(arm_ids=['executed'],selection_rule='Stored4 replay + technical faults; CM001 once gates007/009; no automatic failed-case repeat',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Known CM001/007 replay and gated CM001/007/009',version='v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Initial technical and stored response replay; live stage ledger fixed before live execution',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':None,'sha256':None,'not_applicable_reason':'No new retrieval effect measurement in initial technical gate'})
# Preserve generated merge metadata, fill concrete contributions before implementation.
i=m.get('integration',{});i.update(reason=criteria['hypothesis'],common_invariants=['Same source ACL/version/hash, no gold in product, no outputcap,40/1024/1800 budgets','Research code never imported by serving'],rollback_ref='MAIN112 vector-initial-20261028-r1',no_conflict_reason='1172 changed research transport only;1171 contains product controller; provider retry ownership explicitly moved to gateway for serving.',conflicts=[])
for row in i.get('parent_contributions',[]):row.update(adopted=['1171 product controller' if '1171' in str(row) else '1172 provider policy and validation'],excluded=['GENOS proxy comparison and old4/4 model-output gate'])
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'executed',present,experiment_id=m['experiment_id'],arm_id='executed',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h,n
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
for n in ('common.py','freeze.py','check.py','test_supervisor.py','test_native_supervisor.py','test_supervisor_paging.py','test_source_goals.py','api_fixture_integrated.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_1171'/n).read_text().replace('ADR-1171-source-goal-execution-model-probe','ADR-1173-required-source-server-execution').replace("'controlled'","'executed'")
 (T/n).write_text(s)
print('1173 isolated',len(f['files']),'files; criteria frozen')
