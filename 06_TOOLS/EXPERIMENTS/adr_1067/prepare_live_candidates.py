"""Create A0/A1/A2 research snapshots from the exact B1 rev-002 bytes.

Uses official candidate snapshot/register/freeze operations. It does not edit
the experiment manifest, prior candidates, production code, or selected MAIN.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

from stage_candidate import stage

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1067-non-model-latency-profiling'
CANDIDATES = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1067'
SOURCE = CANDIDATES / 'profile-optimized-r1'
REVISION = 'rev-002'
REVISION_HASH = '477c06206541c89197d62d94839b6cbaa6f170f43c33653b6db928b2ea848a5d'
EXPECTED_FILES = 745
RECEIPT = ADR / 'artifacts/live-candidate-bindings.json'
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as candidate


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def revision_map(directory, revision):
    snapshot = directory / 'revisions' / revision['revision_id'] / 'snapshot'
    require(candidate.canonical_sha256({k: v for k, v in revision.items() if k != 'revision_sha256'})
        == revision['revision_sha256'], 'revision metadata hash mismatch')
    files = {}
    for row in revision['files']:
        path = (ROOT / row['frozen_path']).resolve()
        require(path.is_relative_to(snapshot.resolve()), 'frozen file outside revision')
        name = str(path.relative_to(snapshot))
        require(name not in files and not path.is_symlink(), 'duplicate or symlink source')
        require(sha(path) == row['snapshot_sha256'], 'frozen source changed: ' + name)
        files[name] = row['snapshot_sha256']
    actual = {str(p.relative_to(snapshot)) for p in snapshot.rglob('*') if p.is_file()}
    require(actual == set(files), 'frozen file inventory mismatch')
    return files


def main():
    require(not RECEIPT.exists(), 'live candidate receipt already exists')
    targets = {arm: CANDIDATES / ('action-choice-' + arm.lower() + '-r1') for arm in ('A0', 'A1', 'A2')}
    require(all(not path.exists() for path in targets.values()), 'a live candidate already exists; do not overwrite')
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    plan_path = ADR / 'artifacts/implementation-plan.json'
    plan = read(plan_path)
    require(sha(plan_path) == manifest['design']['criteria_record']['sha256'], 'implementation plan binding changed')
    source_binding = read(ADR / 'artifacts/source-code-binding.json')
    require(source_binding['source'] == plan['source_code'] and len(source_binding['files']) == 743,
        'original source code binding changed')
    require(manifest['reservation']['status'] == 'in_progress', 'ADR is not active')
    parent = manifest['lineage']['parents']
    require(len(parent) == 1 and parent[0]['experiment_id'] == 'ADR-1065-experiment-v1'
        and parent[0]['arm_id'] == 'A2', 'parent must remain completed ADR1065/A2')
    parent_path = ROOT / parent[0]['manifest_path']
    require(sha(parent_path) == parent[0]['manifest_sha256'], 'parent manifest hash changed')
    parent_data = read(parent_path)
    require(parent_data['reservation']['status'] == 'completed'
        and parent_data['results']['status'] == 'complete'
        and parent_data['results']['by_arm']['A2']['status'] == 'complete', 'parent A2 is not complete')
    arms = {row['id']: row for row in manifest['design']['arms']}
    run = next(row for row in manifest['runs'] if row['id'] == 'run-002')
    require(set(run['arm_ids']) == set(targets), 'live run arms changed')
    for arm in targets:
        require(arms[arm]['role'] == 'candidate' and arms[arm]['derived_from'] == ['B1'], 'live arm lineage changed')

    source_manifest_path = SOURCE / 'candidate.json'
    source_manifest = read(source_manifest_path)
    revision = next(row for row in source_manifest['revisions'] if row['revision_id'] == REVISION)
    require(revision['revision_sha256'] == REVISION_HASH and len(revision['files']) == EXPECTED_FILES,
        'B1 rev-002 identity changed')
    expected = revision_map(SOURCE, revision)
    source_root = SOURCE / 'revisions' / REVISION / 'snapshot'
    protected = {str(ROOT / path): value for path, value in plan['preservation'].items()}
    protected.update({str(path): sha(path) for path in (manifest_path, plan_path,
        ADR / 'artifacts/source-code-binding.json', source_manifest_path,
        CANDIDATES / 'profile-baseline-r1/candidate.json')})
    require(all(sha(path) == expected_hash for path, expected_hash in protected.items()), 'preserved source changed')

    present = sorted(name for name in expected if (ROOT / name).is_file())
    absent = sorted(set(expected) - set(present))
    require(all(not os.path.lexists(ROOT / name) for name in absent), 'absent upstream target is not absent')
    bindings = []
    for arm, directory in targets.items():
        created = candidate.snapshot(ADR, directory.name, present,
            experiment_id=manifest['experiment_id'], arm_id=arm, run_ids=['run-002'])
        require(created == directory, 'official snapshot returned an unexpected path')
        # Copy, never hardlink: stage() may rewrite mutable pins/policy in this
        # new snapshot and must not touch the source frozen revision.
        for name in sorted(expected):
            destination = directory / 'snapshot' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / name, destination)
        for name in absent:
            candidate.register_file(directory, name, upstream_state='absent')
        stage(directory.name, True)
        made = read(directory / 'candidate.json')
        frozen = made['revisions'][-1]
        require(len(made['revisions']) == 1, 'new live candidate must have exactly one revision')
        require(revision_map(directory, frozen) == expected, 'live candidate differs from exact B1 rev-002')
        bindings.append({'candidate_id': directory.name, 'manifest_path': str((directory / 'candidate.json').relative_to(ROOT)),
            'manifest_sha256': sha(directory / 'candidate.json'), 'experiment_id': made['experiment_id'],
            'arm_id': arm, 'run_ids': made['run_ids'], 'revision_id': frozen['revision_id'],
            'revision_sha256': frozen['revision_sha256'], 'file_count': len(expected),
            'exact_source_file_map': True})
    require(revision_map(SOURCE, revision) == expected, 'B1 frozen source changed while creating live candidates')
    require(all(sha(path) == expected_hash for path, expected_hash in protected.items()), 'protected artifact changed')
    report = {'schema_version': 'adr1067-live-candidate-bindings-v1', 'status': 'COMPLETE',
        'source': {'manifest_path': str(source_manifest_path.relative_to(ROOT)),
            'manifest_sha256': protected[str(source_manifest_path)], 'revision_id': REVISION,
            'revision_sha256': REVISION_HASH, 'file_count': len(expected),
            'file_map_sha256': candidate.canonical_sha256(expected)},
        'arm_code_bindings': bindings, 'all_file_maps_identical': True,
        'present_upstream_files': len(present), 'absent_upstream_files': len(absent),
        'experiment_manifest_modified': False, 'production_paths_modified': False,
        'preservation_verified': protected, 'model_calls': 0, 'corpus_reads': 0,
        'performance_runs': 0, 'helper_sha256': sha(__file__)}
    with RECEIPT.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': 'COMPLETE', 'file_count_per_arm': len(expected),
        'all_file_maps_identical': True, 'receipt': str(RECEIPT.relative_to(ROOT)),
        'bindings': bindings}, ensure_ascii=False))


if __name__ == '__main__':
    main()
