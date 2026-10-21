from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0874-bounded-followup-continuation';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==83
release=read(R/pointer['manifest_path']);assert all(sha(R/n)==h for n,h in release['files'].items())
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release})
put(D/'data-binding.json',{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256']})
cm=read(R/'02_BACKEND/lawrag/research/candidates/adr_0870/qualified/candidate.json')
put(D/'working-before.json',{x['target_path']:sha(R/x['target_path']) for x in cm['files']})
criteria={'hypothesis':'A missing result for one exact acquisition does not starve a different pending task within the existing two-attempt cap; unread targets remain partial rather than complete.',
 'success':['Bounded independent tasks continue after first no-evidence task','Same exact acquisition across fields/issues executes once with linked receipts','Native PARTIAL/FAILED/missing task receipts cannot become COMPLETE merely because old originals returned','New originals trigger field review; old originals, retry identity, budgets and deadline persist','Resume and duplicate use durable receipts; wrong ACL/hash/state rejected','Unchanged MAIN83 host compression and basis lifecycle regressions pass','Incomplete investigation notice does not request user facts without such a finding'],
 'failure':['Same operation blindly retried','Attempt cap or shared budgets reset/raised','Unverified or foreign sources adopted','Skipped acquisition labeled complete','Existing latest working code lost'],
 'failure_owner':'Existing parent task board owns distinct task scheduling; existing native child owns lookup/read recovery. No new model retry layer.',
 'limits':{'max_distinct_acquisition_attempts':2,'max_model_attempts':40,'wall_seconds':1800,'heavy_workers':1,'rss_gib':8,'address_space_gib':9},
 'evaluation':'Prospective finite software contracts and exact selected-service consumer checks; regression cases from0873 retained separately. Real-model effect tested in separate fresh ADR after this frozen candidate; no legal quality claim.',
 'resource_policy':'Share pinned data and caches; small code snapshot only; one guarded process at a time.'}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','qualified','--experiment-id','ADR-0874-experiment-v1','--arm-id','qualified','--run-id','run-001']
for x in cm['files']:cmd+=['--source',x['target_path']]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Finite execution/state/integrity contracts, not legal quality',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='MAIN83 completed actual observation' if arm['id']=='baseline' else 'Bounded independent research scheduling, exact acquisition receipt status, accurate incomplete notice',controls=['Same MAIN83 data/code except reviewed deltas','No new model calls in this contract qualification','Physical budgets unchanged'])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='bounded-followup-finite-contracts',version='20261018-r1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
why='Finite software/state checks; no model or retrieval quality comparison.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
print('Snapshot current MAIN83 without overwriting recent working changes; two acquisition cap retained')
