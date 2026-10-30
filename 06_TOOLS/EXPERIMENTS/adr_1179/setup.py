from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1179-source-scope-completion-contract';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-1178-source-goal-contained-original'
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary as put
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json')
criteria={'hypothesis':'Before model choice, server turns literal stored article headings matching the user issue into unresolved source goals within current authorized search scope. Completion cannot erase these goals or exclude them through unrelated originals. Acquisition proves bytes, not legal meaning.', 'checks':['Full stored heading matches work across renamed documents, arbitrary coordinates and IDs; no case-specific rule','Current user scope/exclusions/ACL respected; preview, definition-only or unrelated original cannot close a discovered goal','One discovery per bound issue; exact existing lookup/read menu, original verifier, bounded tools/time/model budgets and durable resume retained','Missing/ambiguous/overflow originals retained in limited assessment; no generated legal conclusions','Saved007 false finish/assessment replay routes to undiscovered original; parent263 contracts and paired211 regressions','Actual007 once only after offline pass;009 once only if007 completion gate passes; no automatic retries'], 'failure':'Any ACL/span mismatch, silent unresolved-goal loss, false complete, budget mismatch or new regression stops followup.', 'live_order':['cm-007','cm-009 only after cm-007 passes'], 'per_case_budget':{'physical':40,'tools':1024,'seconds':1800,'output_cap':None}, 'scope':'Isolated candidate only; MAIN112/GENOS unchanged; no001 or stronger model calls', 'limitation':'Literal-heading discovery is a coverage floor, not proof that every semantic dependency was identified.'}
put(D/'criteria.json',criteria)
for n in ['baseline.json','cases.json','corpus.json','authorization.json','provider-policy.json']:
 v=read(P/'artifacts/design'/n)
 if n=='cases.json':v=[c for c in v if c['id'] in ('cm-007','cm-009')]
 put(D/n,v)
put(D/'parent-freeze.json',f)
put(D/'user-authorization.json',{'request':'그럼 필요한 조문을 목표로 안 올리고 충분하다고 끝내는 문제도 고쳐봐. 13조만 하드코딩하지 말고 일반적으로 해결하고, 7번 다시 테스트해서 통과하면 9번도 돌려봐.','session':'01a18102-29c3-78b3-9b53-cc33aaca63e7'})
refs=read(R/'04_EXPERIMENTS/ADR/ADR-1177-response-recovery-followup/artifacts/evaluation-only/cases.json');put(A/'artifacts/evaluation-only/cases.json',[c for c in refs if c['id'] in ('cm-007','cm-009')])
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(A,'scoped',[n for n in f['files'] if (R/n).exists()],experiment_id=m['experiment_id'],arm_id='scoped',run_ids=['run-001']);S=C/'snapshot';known={x['target_path'] for x in read(C/'candidate.json')['files']}
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
 if n not in known:ac.register_file(C,n,upstream_state='absent')
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1178').glob('*.py'):
 if p.name.startswith('test_') or p.name in ['check.py','freeze.py','regression.py']:
  (T/p.name).write_text(p.read_text().replace('ADR-1178-source-goal-contained-original','ADR-1179-source-scope-completion-contract').replace("'contained'","'scoped'"))
for n in ['live.py','gate.py','audit_result.py','audit_storage.py','cm_authorization.py','resource_guard.py','summarize.py']:
 (T/n).write_text((R/'06_TOOLS/EXPERIMENTS/adr_1177'/n).read_text().replace('ADR-1177-response-recovery-followup','ADR-1179-source-scope-completion-contract').replace('ADR-1177','ADR-1179').replace("'continued'","'scoped'"))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual verified original acquisition and honest completion',success_criteria=criteria['checks'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'scoped','role':'candidate','derived_from':['ADR-1178-experiment-v1/contained'],'changes':'Generic server-discovered source goals and guarded closure','controls':'Same data, model, verifier, scope and budgets'}]);m['runs'][0].update(arm_ids=['scoped'],selection_rule='Known007 once;009 only if007 passes; stored response and generic fault tests',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));m['dataset'].update(name='CM007/009 and generic source completion faults',version='v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'),legal_version_checked=False,reference_version_checked=False);m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None,stage_ledger={'mode':'recorded','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),'sha256':'PENDING','not_applicable_reason':None});m['design']['retrieval_stage_plan']['stages_by_arm']={'scoped':['delivered_or_read','original_read','final_cited']}
# Mutable reservation/manifest metadata is not an experiment result file.
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
print('1179 criteria and464-file isolated candidate prepared')
