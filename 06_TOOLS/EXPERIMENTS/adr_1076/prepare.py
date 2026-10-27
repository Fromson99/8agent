"""Freeze prospective criteria, then stage only two changes on selected MAIN104."""
from common import *
from datetime import datetime, timezone
import shutil
import subprocess


def main():
    matrix = ROOT / '06_TOOLS/EXPERIMENTS/adr_1076/finite-matrix.json'
    assert read(matrix)['counts']['total_pairs'] == 1318
    pointer_path = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    pointer = read(pointer_path)
    assert pointer['generation'] == 104
    release = read(ROOT / pointer['manifest_path'])
    assert len(release['files']) == 420
    assert all(sha(ROOT / release['code_root'] / name) == value
               for name, value in release['files'].items())
    criteria = {
        'schema_version': 'adr1076-read-preparation-criteria-v1',
        'frozen_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'One connection_scope.offer_choices invocation may reuse successful acquired_blocks preparation; identical MAIN104 menus, actions, state, source/ACL/generation checks and typed failures.',
        'matrix': bound(matrix),
        'primary': 'Prospectively fixed finite mechanical equivalence census, independently specified before candidate execution.',
        'required': [
            'Every one of1318 matrix pairs produces identical outputs or typed errors, preserving original ordering and state.',
            'Repeated unchanged successful controlled-read preparation with an immutable-store checker performs acquired-original reads only once per preparation.',
            'ACL, source metadata, span value/type/order, control mode, store/session identity changes cannot reuse stale coverage.',
            'Generation checks still run on cache hits; checker failures retain their original typed failure.',
            'No checker, control disabled, empty spans and unsupported/cyclic metadata use the unchanged validation path.',
            'Failures are not cached; output mutation cannot poison coverage; new view or session does not inherit coverage.',
            'Actual offer_choices consumers retain all scope previews, SQL links, grants, menus, actions and failure events.',
            'All420 selected serving files retain MAIN104 bytes except the two declared modules and required dependency hash pins.',
            'Inputs, selected MAIN pointer, source release, model/provider, schemas, prompts, budgets and dataset remain unchanged.'
        ],
        'failure': 'Any mismatch, guard bypass, new incompatible failure, leaked cache lifetime, source mutation, freeze drift or changed policy blocks qualification. Preserve raw failed runs and revise only in a new run/candidate or ADR as applicable.',
        'evaluation_boundary': 'Out-of-sample and decision eligibility apply only to the explicitly finite generated contract census. The known ADR1075 trace is secondary in-sample diagnosis, never a new legal holdout. No legal accuracy or GENOS speed certification.',
        'secondary': {'input': 'Known ADR1075 immutable38-response run or exact saved final investigation state',
                      'scope': 'Separate frozen replay or restored-state comparison after primary census and after parent permits one heavy worker.',
                      'claim': 'Only measured function/window equivalence and latency; not new end-to-end model quality.',
                      'model_calls': 0, 'may_change_primary_criteria': False},
        'failure_contract': {
            'input_consumer': 'Existing view→offer_choices→preview→catalog→acquired_blocks; preview remains the sole recoverable timeout/operational owner.',
            'cache_owner': 'Local CatalogReadPreparation created by offer_choices, never persisted or attached to session/checkpoint.',
            'permission': 'Current session scope and relevant canonical source records are part of the typed key; cache hit still calls store.check_unchanged.',
            'correction': 'None. No invented scope, source, legal conclusion or repaired evidence.',
            'retry': 'No new retry, model call, tool call or deadline. Existing preview failure handling and final error contract preserved.',
            'state': 'Existing journal and partial source receipts preserved; successful cache entries are ephemeral and defensive copies.',
            'exit': 'Original success/menu, recoverable preview failure or original fatal exception; no success on validation failure.'},
        'new_model_calls': 0, 'network': False, 'synthetic_max_address_space_bytes': 1073741824,
        'real_data_parallel_workers': 1,
        'rollback': 'Official activation rollback to immutable MAIN104 bytes; preserve append-only receipts and failed histories.'}
    put(DESIGN / 'criteria.json', criteria)
    put(DESIGN / 'finite-matrix.json', read(matrix))
    put(DESIGN / 'baseline.json', {'pointer': pointer, 'pointer_sha256': sha(pointer_path), 'manifest': release})
    put(DESIGN / 'working-before.json', {name: sha(ROOT/name) for name in release['files']})
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    manifest['decision_eligible'] = True
    manifest['lineage']['hypothesis_delta'] = criteria['scope']
    manifest['design'].update(hypothesis=criteria['scope'], primary_metric=criteria['primary'],
        success_criteria=criteria['required'], failure_criteria=criteria['failure'], criteria_frozen_before_run=True)
    manifest['design']['code_isolation'].update(mode='candidate_snapshot', reason=None, candidates=[])
    for arm in manifest['design']['arms']:
        arm['changes'] = ('Immutable selected MAIN104 implementation' if arm['id'] == 'baseline'
                          else 'MAIN104 plus invocation-local successful acquired-read preparation in two modules; no menu or policy change')
        arm['controls'] = criteria['evaluation_boundary']
    manifest['runs'][0].update(selection_rule='Complete1318-pair frozen synthetic Cartesian census; no result-based selection',
        artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
    manifest['dataset'].update(name='Independent prospective read-preparation contract census', version='read-preparation-v1',
        frozen_source=str((DESIGN/'finite-matrix.json').relative_to(ROOT)), sha256=sha(DESIGN/'finite-matrix.json'),
        legal_version_checked=True, reference_version_checked=True)
    manifest['llm_policy']['llm_calls'] = []
    reason = 'Deterministic tiny generated source/permission/menu contracts; primary census has no real corpus retrieval, model, legal answer or ranking change.'
    manifest['retrieval_accounting']['not_applicable_reason'] = reason
    manifest['retrieval_accounting']['stage_ledger']['not_applicable_reason'] = reason
    put(manifest_path, manifest, replace=True)
    # Existing working-tree edits are upstream provenance only. Rebase every
    # serving byte onto selected MAIN104 before changing the two target modules.
    command = [str(ROOT/'.venv/bin/python'), '06_TOOLS/run_tool.py', 'adr_candidate.py', 'snapshot',
        '--adr', str(ADR), '--candidate-id', CANDIDATE.name, '--experiment-id', manifest['experiment_id'],
        '--arm-id', 'optimized', '--run-id', 'run-001']
    for name in sorted(release['files']):
        command += ['--source', name]
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    for name in release['files']:
        shutil.copyfile(ROOT/release['code_root']/name, CANDIDATE/'snapshot'/name)
    put(DESIGN/'staging.json', {'candidate': str(CANDIDATE.relative_to(ROOT)),
        'targets': TARGETS, 'serving_files': len(release['files']), 'source': 'Immutable MAIN104',
        'product_changed': False, 'tests_executed': 0, 'new_model_calls': 0})
    print('Prospective1318-case criteria frozen; MAIN104 snapshot staged; candidate tests0/model0')


if __name__ == '__main__':
    main()
