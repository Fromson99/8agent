"""Prepare mutable ADR1068 candidates from exact ADR1067 rev-002 bytes.

Uses official snapshot/register operations and deliberately never freezes,
stages, imports product code, executes tests, or changes an old candidate.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1068-startup-latency-attribution'
SOURCES = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1067'
TARGETS = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1068'
RECEIPT = ADR / 'artifacts/candidate-source-bindings.json'
REVISION = 'rev-002'
ARMS = {
    'B0': ('profile-baseline-r1', 744,
        '1e3749f541ab5efc466393ff1c9d487758c1a093b8122ae8d4b037dbce7494a8'),
    'B1': ('profile-optimized-r1', 745,
        '477c06206541c89197d62d94839b6cbaa6f170f43c33653b6db928b2ea848a5d'),
}
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


def file_map(snapshot):
    result = {}
    for path in sorted(snapshot.rglob('*')):
        require(not path.is_symlink(), 'snapshot symlink: ' + str(path))
        if path.is_file():
            result[path.relative_to(snapshot).as_posix()] = sha(path)
        else:
            require(path.is_dir(), 'snapshot special file: ' + str(path))
    return result


def source_binding(name, expected_count, expected_revision_hash):
    manifest_path = SOURCES / name / 'candidate.json'
    data = read(manifest_path)
    revision = next(row for row in data['revisions'] if row['revision_id'] == REVISION)
    require(revision['revision_sha256'] == expected_revision_hash,
        'source revision identity changed: ' + name)
    require(candidate.canonical_sha256({k: v for k, v in revision.items()
        if k != 'revision_sha256'}) == expected_revision_hash, 'revision metadata changed')
    snapshot = SOURCES / name / 'revisions' / REVISION / 'snapshot'
    expected = {}
    for row in revision['files']:
        path = ROOT / row['frozen_path']
        require(path.resolve().is_relative_to(snapshot.resolve()), 'frozen path escaped source')
        relative = path.relative_to(snapshot).as_posix()
        require(relative not in expected, 'duplicate source target')
        expected[relative] = row['snapshot_sha256']
    require(len(expected) == expected_count and file_map(snapshot) == expected,
        'source frozen file inventory changed: ' + name)
    return manifest_path, snapshot, expected


def main():
    require(not RECEIPT.exists(), 'receipt already exists; do not overwrite')
    require(all(not (TARGETS / row[0]).exists() for row in ARMS.values()),
        'candidate already exists; do not overwrite or automatically resume')
    experiment_path = ADR / '실험/manifest.json'
    experiment = read(experiment_path)
    require(experiment['experiment_id'] == 'ADR-1068-experiment-v1'
        and experiment['reservation']['status'] == 'in_progress', 'incorrect or inactive ADR')
    parents = experiment['lineage']['parents']
    require(len(parents) == 1 and parents[0]['experiment_id'] == 'ADR-1065-experiment-v1'
        and parents[0]['arm_id'] == 'A2', 'parent must be completed ADR1065/A2')
    parent_path = ROOT / parents[0]['manifest_path']
    require(sha(parent_path) == parents[0]['manifest_sha256'], 'parent manifest changed')
    parent = read(parent_path)
    require(parent['reservation']['status'] == 'completed'
        and parent['results']['status'] == 'complete'
        and parent['results']['by_arm']['A2']['status'] == 'complete', 'parent is incomplete')
    informed = [row for row in experiment['relationships']
        if row['adr_id'] == 'ADR-1067' and row['relation'] == 'informed_by']
    require(len(informed) == 1 and sha(ROOT / informed[0]['record_path'])
        == informed[0]['record_sha256'], 'ADR1067 reference binding changed')
    declared = {row['id']: row for row in experiment['design']['arms']}
    run = next(row for row in experiment['runs'] if row['id'] == 'run-001')
    require(all(declared[arm]['role'] == 'candidate' and arm in run['arm_ids']
        for arm in ARMS), 'arm/run linkage changed')

    # Old candidate manifests and every source frozen byte must remain intact.
    protected = {str(path.relative_to(ROOT)): sha(path)
        for path in SOURCES.glob('*/candidate.json')}
    for path in (experiment_path, ADR / 'claim.json',
            ADR / 'artifacts/implementation-plan.json'):
        protected[str(path.relative_to(ROOT))] = sha(path)
    protected[str(parent_path.relative_to(ROOT))] = sha(parent_path)
    protected[informed[0]['record_path']] = informed[0]['record_sha256']
    active_main = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    protected[str(active_main.relative_to(ROOT))] = sha(active_main)
    prepared = {arm: source_binding(*row) for arm, row in ARMS.items()}
    bindings = []
    for arm, (name, count, revision_hash) in ARMS.items():
        source_manifest, source, expected = prepared[arm]
        present = sorted(name for name in expected if (ROOT / name).is_file())
        absent = sorted(set(expected) - set(present))
        require(all(not os.path.lexists(ROOT / name) for name in absent),
            'absent upstream path exists')
        destination = candidate.snapshot(ADR, name, present,
            experiment_id=experiment['experiment_id'], arm_id=arm, run_ids=['run-001'])
        require(destination == TARGETS / name, 'official snapshot returned unexpected path')
        for relative in sorted(expected):
            output = destination / 'snapshot' / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            # Mutable destinations must never share an inode with frozen input.
            shutil.copy2(source / relative, output)
        for relative in absent:
            candidate.register_file(destination, relative, upstream_state='absent')
        made = read(destination / 'candidate.json')
        require(made['revisions'] == [] and made['production_loadable'] is False,
            'new candidate must remain unfrozen and research-only')
        require({row['target_path'] for row in made['files']} == set(expected)
            and file_map(destination / 'snapshot') == expected,
            'new candidate differs from exact source file map')
        for row in made['files']:
            target = ROOT / row['target_path']
            require((row['upstream_state'] == 'present' and sha(target) == row['upstream_sha256'])
                or (row['upstream_state'] == 'absent' and not os.path.lexists(target)),
                'upstream changed during candidate preparation')
        bindings.append({'arm_id': arm, 'run_ids': ['run-001'], 'candidate_id': name,
            'manifest_path': str((destination / 'candidate.json').relative_to(ROOT)),
            'manifest_sha256_at_preparation': sha(destination / 'candidate.json'),
            'snapshot_path': str((destination / 'snapshot').relative_to(ROOT)),
            'source_manifest_path': str(source_manifest.relative_to(ROOT)),
            'source_manifest_sha256': sha(source_manifest), 'source_revision_id': REVISION,
            'source_revision_sha256': revision_hash, 'source_file_map': expected,
            'file_map_sha256': candidate.canonical_sha256(expected),
            'exact_source_file_map': True, 'file_count': count,
            'upstream_present_files': len(present), 'upstream_absent_files': len(absent),
            'frozen': False})
    for arm, row in ARMS.items():
        source_binding(*row)
    require(all(sha(ROOT / path) == value for path, value in protected.items()),
        'protected artifact changed during preparation')
    report = {'schema_version': 'adr1068-candidate-source-bindings-v1',
        'status': 'PREPARED_UNFROZEN', 'experiment_id': experiment['experiment_id'],
        'parent': parents[0], 'informed_by': informed[0], 'candidates': bindings,
        'note': 'Present upstream provenance remains the official working-root snapshot. '
            'The mutable file contents are the recorded frozen source overlay. '
            'Later official freeze refreshes current snapshot hashes; no revision exists yet.',
        'protected_hashes': protected, 'helper_sha256': sha(__file__),
        'experiment_manifest_modified_by_helper': False, 'production_paths_modified': False,
        'freeze_executed': False, 'tests_executed': 0, 'model_calls': 0, 'corpus_reads': 0}
    with RECEIPT.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'receipt': str(RECEIPT.relative_to(ROOT)),
        'bindings': [{k: v for k, v in row.items() if k != 'source_file_map'}
            for row in bindings]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
