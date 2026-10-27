"""Freeze prospective SQL criteria, then derive one SQL edit from observed failed1078."""
from common import *
from datetime import datetime, timezone
import shutil
import subprocess

PARENT = ROOT/'04_EXPERIMENTS/ADR/ADR-1078-navigation-bound-replay'
parent_manifest = read(PARENT/'실험/manifest.json')
assert parent_manifest['reservation']['status'] == 'completed'
assert parent_manifest['results']['status'] == 'failed'
assert parent_manifest['results']['by_arm']['optimized']['status'] == 'failed'
assert (PARENT/'artifacts/final-validation.txt').read_text().startswith('OK:')
parent_freeze = read(PARENT/'artifacts/design/freeze.json')
parent_code = ROOT/parent_freeze['code_root']
assert all(sha(ROOT/p) == h for p,h in parent_freeze['files'].items())
matrix_source = ROOT/'06_TOOLS/EXPERIMENTS/adr_1080/sql-matrix.json'
matrix = read(matrix_source)
count = matrix['counts']['total_pairs']
pointer_path = ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
pointer = read(pointer_path)
release = read(ROOT/pointer['manifest_path'])
assert pointer['generation'] == 104 and len(release['files']) == 420
assert all(sha(ROOT/release['code_root']/name) == value for name,value in release['files'].items())
old_sql = "view(name, 'original.reference_id IN (SELECT id FROM temp.reference)')"
new_sql = "view(name, 'EXISTS (SELECT 1 FROM temp.reference r WHERE r.id=original.reference_id)')"
assert (parent_code/SQL_TARGET).read_text().count(old_sql) == 1
criteria = {'schema_version':'adr1080-visible-reference-point-criteria-v1',
    'frozen_at':datetime.now(timezone.utc).isoformat(),
    'scope':'Replace only the common4TEMPview membership predicate with a correlated EXISTS through the same authorized temp.reference; keep the observed1078preparation and existing catalog SQL unchanged.',
    'matrix':bound(matrix_source),'paired_cases':count,
    'primary':'Prospective finite SQL result/error and consumer-order contracts for the four reference visibility views; not legal-quality holdout.',
    'required':[
        'All declared fixture pairs preserve all four view projections, outer duplicates, NULL/orphan/missing/hidden membership and input/mainDB bytes.',
        'Existing catalog DISTINCT JSON, source filtering, cursor, only_references, ORDER BY and LIMIT outputs remain exact.',
        'Latest-only/excluded-empty actual activation and completely empty selection early-return are separately covered.',
        'Requested malformed rows and required missing-relation errors keep exact exception type/message; no swallowing or fabricated empty success.',
        'EXPLAIN active compact membership replaces a global reference_payload list scan with correlated ID lookup; opcode counts are not performance evidence.',
        'Only search_selection.py one declared SQL replacement and its dependency pins differ from the observed1078candidate.',
        'The cumulative serving derivative differs from selected MAIN104 only in3source modules and31pins; original source/ACL/witness/generation validators remain byte-identical to1078.',
        'Native known replay must meet its separately frozen full38protectedrequests/35frames/finalanswer contract and window timing conditions.',
        'No data/profile/schema/prompt/model/search/action/menu/budget change; MAIN104 and working code unchanged during evaluation.'
    ],
    'failure':'Any declared mismatch, broadened visibility, lost row/order/cursor/limit, invalid requested error, new undeclared source change or freeze drift blocks qualification. Preserve failures and revise only in a fresh run/candidate/ADR.',
    'schema_boundary':'Published generation schema uses TEXT reference IDs and ordinary BINARY collation; custom collation/affinity schema is not generalized.',
    'corruption_boundary':'Valid published generation selection and requested-row failures only. The old global ID scan can encounter unrelated malformed JSON that a correlated lookup never requests; those global unrequested scan-only exceptions are not claimed equivalent. Ingestion, publication integrity and immutable generation checks remain responsible for global corpus validity.',
    'evidence_boundary':'SQL fixture checks membership/consumer rows and requested SQL errors. Unchanged downstream source/witness code hashes and native original frames support their connection; this matrix is not a new exhaustive legal or witness-quality evaluation.',
    'eligibility':'Out-of-sample decision eligibility applies only to these new predeclared finite SQL contracts. Known response replay and earlier1076/1078results are supporting in-sample evidence.',
    'observed_code_comparator':bound(PARENT/'실험/manifest.json'),
    'cache_evidence':'Preparation code already observed in1076(1318pairs) and1078(280pairs). Both whole arms failed strict secondary replay. Those are disclosed supporting contracts, not completed parents, fresh SQL cases, or fresh cache holdouts.',
    'new_model_calls':0,'network_allowed':False,'max_address_space_bytes':1073741824,
    'heavy_workers':1,'rollback':'Official MAIN rollback to immutable selected104; preserve failed histories.'}
put(DESIGN/'criteria.json',criteria)
put(DESIGN/'sql-matrix.json',matrix)
put(DESIGN/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(pointer_path),'manifest':release})
put(DESIGN/'observed-comparator.json',{'source':bound(PARENT/'실험/manifest.json'),
    'readme':bound(PARENT/'README.md'),'arm':'optimized','status':'FAILED_OBSERVED_NOT_COMPLETED_PARENT','freeze':bound(PARENT/'artifacts/design/freeze.json'),
    'code_root':parent_freeze['code_root'],'serving_files':parent_freeze['serving_files'],
    'primary_result':bound(PARENT/'artifacts/run-001/result.json'),
    'secondary_result':bound(PARENT/'artifacts/run-002/result.json')})
put(DESIGN/'working-before.json',{name:sha(ROOT/name) for name in release['files']})
manifest = read(ADR/'실험/manifest.json')
assert manifest['lineage']['parents'][0]['experiment_id'] == 'ADR-1075-experiment-v1'
assert manifest['lineage']['parents'][0]['arm_id'] == 'observed'
completed_parent = manifest['lineage']['parents'][0]
assert sha(ROOT/completed_parent['manifest_path']) == completed_parent['manifest_sha256']
manifest['lineage']['hypothesis_delta'] = criteria['scope']
manifest['relationships'].append({'adr_id':'ADR-1078','experiment_id':parent_manifest['experiment_id'],
    'relation':'informed_by','record_path':str((PARENT/'실험/manifest.json').relative_to(ROOT)),
    'record_sha256':sha(PARENT/'실험/manifest.json'),
    'note':'Failed whole arm preserved. Exact candidate bytes and already-observed280state contracts are supporting evidence; not a completed parent or new holdout.'})
manifest['decision_eligible'] = True
manifest['design'].update(hypothesis=criteria['scope'],primary_metric=criteria['primary'],
    success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,
    observed_comparator=bound(DESIGN/'observed-comparator.json'))
manifest['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in manifest['design']['arms']:
    arm.update(derived_from=['ADR-1075-experiment-v1/observed'] if arm['id']=='baseline' else ['baseline'],
        changes='MAIN104 plus observed failed1078 preparation bytes as SQL comparator; failed lineage is not promoted' if arm['id']=='baseline' else 'Same observed preparation plus one shared membership SQL predicate and exact pins',
        controls=criteria['eligibility'])
manifest['runs'][0].update(selection_rule=f'All{count}predeclared SQL fixture pairs and declared consumer queries; no post-result pruning',
    artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
manifest['dataset'].update(name='Four-view reference visibility finite SQL contracts',version='reference-point-v1',
    frozen_source=str((DESIGN/'sql-matrix.json').relative_to(ROOT)),sha256=sha(DESIGN/'sql-matrix.json'),
    legal_version_checked=True,reference_version_checked=True)
manifest['llm_policy']['llm_calls'] = []
reason = 'Finite synthetic SQL visibility/NULL/orphan/ordering contracts, no corpus retrieval or legal answer scoring. Known native replay is separate in-sample secondary.'
manifest['retrieval_accounting']['not_applicable_reason'] = reason
manifest['retrieval_accounting']['stage_ledger']['not_applicable_reason'] = reason
put(ADR/'실험/manifest.json',manifest,replace=True)
command = [str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot',
    '--adr',str(ADR),'--candidate-id',CANDIDATE.name,'--experiment-id',manifest['experiment_id'],
    '--arm-id','optimized','--run-id','run-001']
for name in sorted(release['files']):command += ['--source',name]
subprocess.run(command,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
stage = CANDIDATE/'snapshot'
for name in release['files']:shutil.copyfile(parent_code/name,stage/name)
assert all(sha(stage/name) == h for name,h in parent_freeze['serving_files'].items())
sql = (stage/SQL_TARGET).read_text()
(stage/SQL_TARGET).write_text(sql.replace(old_sql,new_sql,1))
pipeline = read(stage/'00_SYSTEM/PIPELINE.json')
pin_paths = {'00_SYSTEM/PIPELINE.json'}
for ref in pipeline['engines'].values():
    path = stage/ref['manifest']
    engine = read(path)
    if SQL_TARGET in engine['files']:
        engine['files'][SQL_TARGET] = sha(stage/SQL_TARGET)
        put(path,engine,replace=True)
        ref['sha256'] = sha(path)
        pin_paths.add(ref['manifest'])
put(stage/'00_SYSTEM/PIPELINE.json',pipeline,replace=True)
parent_changes = {name for name,h in parent_freeze['serving_files'].items() if sha(stage/name)!=h}
main_changes = {name for name,h in release['files'].items() if sha(stage/name)!=h}
assert parent_changes == {SQL_TARGET}|pin_paths and len(parent_changes)==32
assert main_changes == set(TARGETS)|pin_paths and len(main_changes)==34
put(DESIGN/'candidate-preparation.json',{'source_targets':TARGETS,'new_sql_target':SQL_TARGET,
    'old_sql':old_sql,'new_sql':new_sql,'pin_paths':sorted(pin_paths),
    'changed_from_observed_comparator':sorted(parent_changes),'changed':sorted(main_changes),
    'serving_files':{name:sha(stage/name) for name in release['files']},
    'primary_comparator':parent_freeze['code_root'],'selected_release_rebase':release['code_root'],
    'scope':'One SQL predicate changes four temp views; catalog query, cache, permission/source/witness/generation validation unchanged.'})
print('Prospective',count,'SQL pairs; observed1078derivative staged;1newSQL/3cumulativeproducts; execution0')
