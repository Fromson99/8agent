"""Prospective new state-boundary criteria and byte-identical product staging."""
from common import *
from datetime import datetime, timezone
import shutil
import subprocess

matrix_path = ROOT/'06_TOOLS/EXPERIMENTS/adr_1078/state-matrix.json'
matrix = read(matrix_path)
count = matrix['counts']['total_pairs']
assert count > 0
old = ROOT/'04_EXPERIMENTS/ADR/ADR-1076-navigation-view-preparation-reuse'
old_freeze = read(old/'artifacts/design/freeze.json')
old_code = ROOT/old_freeze['code_root']
assert read(old/'실험/manifest.json')['results']['status'] == 'failed'
assert all(sha(ROOT/p) == h for p,h in old_freeze['files'].items())
pointer_path = ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
pointer = read(pointer_path)
release = read(ROOT/pointer['manifest_path'])
assert pointer['generation'] == 104 and len(release['files']) == 420
assert all(sha(ROOT/release['code_root']/name) == value for name,value in release['files'].items())
criteria = {'schema_version':'adr1078-composed-state-criteria-v1',
    'frozen_at':datetime.now(timezone.utc).isoformat(),
    'scope':'Qualify the unchanged two-module invocation-local preparation against newly specified composed state boundaries; retain original menus, originals, permissions, errors and execution lifetime.',
    'matrix':bound(matrix_path),'paired_cases':count,
    'primary':'New prospective finite composed-state mechanical contracts, distinct from the observed1318single/static cases; not legal-quality holdout.',
    'required':[
        'Every predeclared new paired state trace preserves each output or typed failure, source/permission state, and caller-owned state.',
        'Partial verification failure, repeated failure and later repair cannot install or resurrect invalid cache entries.',
        'Interleaved sessions/stores, layered input mutations and preparation lifetime boundaries retain fresh verification and immutable-store checks.',
        'Every declared state sequence is executed in both arms; no result-based pruning or new expected-output repair.',
        'Candidate product420servingfiles are byte-identical to ADR1076 frozen candidate; selected MAIN104 differs only in the same2modules and31pins.',
        'The prior1318passedpairs are observed supporting evidence only; never count them as new independent cases.',
        'Frozen files, current MAIN pointer, dataset/profile/schema/prompt/model/budgets and working code remain unchanged.'
    ],
    'failure':'Any mismatched output/error/state, stale reuse, omitted sequence, unbound input or product-code drift blocks qualification. Preserve failures and use a new run/candidate/ADR for corrections as required.',
    'evaluation_boundary':'Decision eligibility and out-of-sample apply only to the prospectively declared new finite mechanical state sequences. Known ADR1075 responses and ADR1076observedprimary/35viewtiming are in-sample supporting evidence, not new legal-quality or independent speed measurements.',
    'secondary':'New native optimized replay must satisfy its separately frozen journal-bound server identity contract and all original38responses/35frames/finalanswer. Historical baseline35viewsegment may be compared only for view time, never completed-service or totalrequest speed.',
    'failure_owner':'Existing preview owns recoverable timeout/operational failures; no new correction/retry/tool/model behavior. Original immutable store check_unchanged contract remains required.',
    'max_address_space_bytes':1073741824,'new_model_calls':0,'network_allowed':False,
    'actual_corpus_workers':1,'rollback':'Official rollback to immutable MAIN104 with new receipt.'}
put(DESIGN/'criteria.json',criteria)
put(DESIGN/'state-matrix.json',matrix)
put(DESIGN/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(pointer_path),'manifest':release})
put(DESIGN/'working-before.json',{name:sha(ROOT/name) for name in release['files']})
put(DESIGN/'prior-observed-evidence.json',{'status':'OBSERVED_NOT_NEW_HOLDOUT',
    'failed_source':bound(old/'실험/manifest.json'),'prior_primary':bound(old/'artifacts/run-001/result.json'),
    'prior_secondary_failure':bound(old/'artifacts/run-002/result.json'),
    'prior_product_freeze':bound(old/'artifacts/design/freeze.json'),
    'product_code_root':old_freeze['code_root'],
    'prior_case_count':1318,'use':'Existing finite-contract evidence and preserved failed reconstruction; no completed parent or accepted promotion source is claimed.'})
manifest = read(ADR/'실험/manifest.json')
manifest['decision_eligible'] = True
manifest['lineage']['hypothesis_delta'] = criteria['scope']
manifest['design'].update(hypothesis=criteria['scope'],primary_metric=criteria['primary'],
    success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,
    prior_observed_evidence=bound(DESIGN/'prior-observed-evidence.json'))
manifest['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in manifest['design']['arms']:
    arm['changes'] = 'Immutable selected MAIN104' if arm['id']=='baseline' else 'Exact420filebytes of prior ADR1076 candidate; no new product modification; same2modules and31pins over MAIN104'
    arm['controls'] = criteria['evaluation_boundary']
manifest['runs'][0].update(selection_rule=f'All{count}new prospective composed-state pairs; no post-result selection',
    artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
manifest['dataset'].update(name='New prospective composed-state boundary contracts',version='composed-state-v1',
    frozen_source=str((DESIGN/'state-matrix.json').relative_to(ROOT)),sha256=sha(DESIGN/'state-matrix.json'),
    legal_version_checked=True,reference_version_checked=True)
manifest['llm_policy']['llm_calls'] = []
reason = 'New finite synthetic state-composition contracts; no real corpus retrieval/model/legal answer/ranking change in primary. Native known replay is separate in-sample secondary.'
manifest['retrieval_accounting']['not_applicable_reason'] = reason
manifest['retrieval_accounting']['stage_ledger']['not_applicable_reason'] = reason
put(ADR/'실험/manifest.json',manifest,replace=True)
command = [str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot',
    '--adr',str(ADR),'--candidate-id',CANDIDATE.name,'--experiment-id',manifest['experiment_id'],
    '--arm-id','optimized','--run-id','run-001']
for name in sorted(release['files']):
    command += ['--source',name]
subprocess.run(command,cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
for name in release['files']:
    shutil.copyfile(old_code/name,CANDIDATE/'snapshot'/name)
assert all(sha(CANDIDATE/'snapshot'/name) == h for name,h in old_freeze['serving_files'].items())
put(DESIGN/'staging.json',{'candidate':str(CANDIDATE.relative_to(ROOT)),
    'serving_files':420,'source_code_root':old_freeze['code_root'],
    'source_freeze':bound(old/'artifacts/design/freeze.json'),'all_product_bytes_identical_to_prior_candidate':True,
    'source_targets':TARGETS,'product_changes_in_this_adr':0,'tests_executed':0,'new_model_calls':0})
print('New prospective',count,'paired-state criteria and byte-identical420filecandidate staged; execution0')
