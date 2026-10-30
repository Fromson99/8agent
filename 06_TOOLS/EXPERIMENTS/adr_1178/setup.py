from pathlib import Path
import json,hashlib,shutil,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1178-source-goal-contained-original';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-1176-response-contract-route-recovery'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');m=read(A/'실험/manifest.json')
criteria={'hypothesis':'A completed ancestor read can satisfy a uniquely bound child goal only when same document/scope, actual ancestry, full child spans and unchanged originals are proved.','checks':['No duplicate read/lookup for fully acquired child original','Partial child receipt, other document/scope/sibling, ambiguous coordinate and hash mismatch cannot satisfy','Completed exact target behavior unchanged;247prior contracts retained','Replay actual007 stored ancestor receipt and missing-block fault; no new model calls'],'failure':'Any false ACQUIRED, inferred legal meaning, lost receipt/ACL or new regression fails.','new_model_calls':0,'scope':'Offline correction after007failed. Do not rerun007 or start009. MAIN112 unchanged.','authorization':'User 전체 수정 and retest; deterministic newly observed source receipt defect repaired without further live calls.'}
put(D/'criteria.json',criteria)
for n in ['baseline.json','cases.json','corpus.json','authorization.json','provider-policy.json']:put(D/n,read(P/'artifacts/design'/n))
put(D/'parent-freeze.json',f);put(D/'observed-defect.json',read(R/'04_EXPERIMENTS/ADR/ADR-1177-response-recovery-followup/artifacts/ancestor-receipt-observation.json'))
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(A,'contained',[n for n in f['files'] if (R/n).exists()],experiment_id=m['experiment_id'],arm_id='contained',run_ids=['run-001']);S=C/'snapshot';known={x['target_path'] for x in read(C/'candidate.json')['files']}
for n,h in f['files'].items():
 assert sha(R/f['code_root']/n)==h
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/f['code_root']/n,S/n)
 if n not in known:ac.register_file(C,n,upstream_state='absent')
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1176').glob('*.py'):
 if p.name.startswith('test_') or p.name in ['common.py','check.py','freeze.py','regression.py']:
  (T/p.name).write_text(p.read_text().replace('ADR-1176-response-contract-route-recovery','ADR-1178-source-goal-contained-original').replace("'repaired'","'contained'"))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Verified child source completeness from existing ancestor receipts',success_criteria=criteria['checks'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'contained','role':'candidate','derived_from':['ADR-1176-experiment-v1/repaired'],'changes':'Exact original containment proof in source_goal_control.refresh only','controls':'Same data/schema/model/budget and strict source verifier'}]);m['runs'][0].update(arm_ids=['contained'],selection_rule='247parent contracts plus contained-source faults and saved007 original receipt',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));m['dataset'].update(name='Stored007 ancestor original and synthetic containment faults',version='v1',frozen_source=str((D/'observed-defect.json').relative_to(R)),sha256=sha(D/'observed-defect.json'),legal_version_checked=False,reference_version_checked=False);m['llm_policy']['llm_calls']=[];m['retrieval_accounting'].update(changed=False,not_applicable_reason='Offline receipt completeness validation only; no new retrieval or model selection',stage_ledger={'mode':'not_applicable','not_applicable_reason':'Existing original receipt replay and synthetic state faults; no retrieval stages'});put(A/'실험/manifest.json',m)
print('1178criteria frozen, isolated same464 parent')
