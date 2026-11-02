from common import *
import shutil,sqlite3
DES.mkdir(parents=True,exist_ok=True)
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1278-review-explanation-whatif-live';prior=parent/'artifacts';f=read(prior/'design/freeze.json')
for name in ('source.json','baseline.json','cases.json','authorization.json','ontology-input.json','ontology-config.json'):
 put(DES/name,read(prior/'design'/name))
criteria=read(prior/'design/criteria.json');criteria.update(continuation='No initial regeneration. Use committed original state and new prefixed operation IDs. One semantic branch at most. Product code identical to1278. Original record write collision fixed only in new runner; preserve all1278 outcomes.',limits={**criteria['limits'],'physical_model_calls_total':12})
put(DES/'criteria.json',criteria)
runtime=prior/'live/review-whatif/runtime';backup=ART/'parent-runtime-snapshot';shutil.copytree(runtime,backup)
previous=read(prior/'live/review-whatif/audit.json')
put(DES/'continuation.json',{'runtime':str(runtime.relative_to(ROOT)),'inherited_attempt_ids':[x['attempt_id'] for x in previous['attempts']],
 'inherited_physical_calls':3,'parent_runtime_snapshot':str(backup.relative_to(ROOT)),'snapshot_files':{str(p.relative_to(backup)):sha(p) for p in backup.rglob('*') if p.is_file()},
 'preservation':'Parent reported outputs/raw remain immutable. Shared original case ledger is extended through normal API only; backup freezes pre-continuation tables. Original case facts/head/answer must remain equal.'})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='Fix append-only experiment recording and continue unexecuted numeric/semantic branches from completed real answer, without regenerating baseline.'
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='actual stored-baseline branch preservation and numeric/semantic outcomes',success_criteria=criteria['success'],failure_criteria=[criteria['failure']],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed ADR1278 real baseline plus recorder failure',controls='Stored answer inherited, no new baseline generation')
m['design']['arms'][1].update(changes='Experiment recorder only; product522 identical',controls='Same source, ontology publication, original case and model policy; new operations separately recorded')
m['runs'][0].update(arm_ids=['verified'],artifact_path=str((RUN/'result.json').relative_to(ROOT)),selection_rule='Continue frozen1278 unexecuted branch steps once; baseline physical calls forbidden')
m['dataset'].update(name='Inherited synthetic cost/approval regulation and committed case',version='20261102-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
reason='Functional continuation without retrieval implementation/effect comparison';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
assert all(sha(ROOT/n)==h for n,h in f['files'].items()),'working product drift'
S=ac.snapshot(ADR,'verified',sorted(f['files']),experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'])/'snapshot'
put(DES/'working-before.json',{n:sha(ROOT/n) for n in f['files']});put(DES/'candidate-path.json',{'snapshot':str(S.relative_to(ROOT))})
print('Prepared unchanged',len(f['files']),'files and preserved baseline runtime')
