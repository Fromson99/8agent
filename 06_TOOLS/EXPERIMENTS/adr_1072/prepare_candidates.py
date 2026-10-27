"""Prepare an exact ADR1071 B1 revision copy; registration/freeze follow profiling.

Only official snapshot creation and byte-preserving copies run here. No product,
model, corpus, profiling or test execution occurs.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1072-definition-link-visibility-point-check'
BASE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1071/profile-optimized-r1'
DEST = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1072/profile-optimized-r2'
REVISION = 'rev-001'
BASE_HASH = '4c9f6cbdd859a5ae1bfe7749b0fe1c179373e5fc1c8c0645d3b26ad5df2a11f8'
POLICY = '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as candidate


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def files(root):
    result = {}
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'symlink in snapshot')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
        else:
            require(path.is_dir(), 'special file in snapshot')
    return result


def frozen():
    manifest = read(BASE / 'candidate.json')
    require(manifest['experiment_id'] == 'ADR-1071-experiment-v1'
        and manifest['arm_id'] == 'B1' and manifest['run_ids'] == ['run-001'],
        'wrong source candidate binding')
    revision = next(r for r in manifest['revisions'] if r['revision_id'] == REVISION)
    actual_hash = candidate.canonical_sha256({k:v for k,v in revision.items() if k != 'revision_sha256'})
    require(actual_hash == revision['revision_sha256'] == BASE_HASH, 'source revision metadata changed')
    root = BASE / 'revisions' / REVISION / 'snapshot'
    expected = {}
    for row in revision['files']:
        path = ROOT / row['frozen_path']
        require(path.resolve().is_relative_to(root.resolve()), 'source path escapes revision')
        relative = path.relative_to(root).as_posix()
        require(relative not in expected, 'duplicate source path')
        expected[relative] = row['snapshot_sha256']
    require(len(expected) == 747 and files(root) == expected, 'source file inventory changed')
    return root, expected


def main():
    require(not DEST.exists(), 'candidate exists; never overwrite or silently resume')
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    require(manifest['experiment_id'] == 'ADR-1072-experiment-v1'
        and manifest['reservation']['status'] == 'in_progress', 'incorrect or inactive ADR')
    parents = manifest['lineage']['parents']
    require(len(parents) == 1 and parents[0]['experiment_id'] == 'ADR-1065-experiment-v1'
        and parents[0]['arm_id'] == 'A2', 'wrong parent')
    parent_path = ROOT / parents[0]['manifest_path']
    require(sha(parent_path) == parents[0]['manifest_sha256'], 'parent manifest changed')
    parent = read(parent_path)
    require(parent['reservation']['status'] == 'completed'
        and parent['results']['by_arm']['A2']['status'] == 'complete', 'parent is incomplete')
    relation = next(r for r in manifest['relationships'] if r['adr_id'] == 'ADR-1071')
    relation_path = ROOT / relation['record_path']
    require(relation['relation'] == 'informed_by'
        and sha(relation_path) == relation['record_sha256'], 'source relationship changed')
    plan = ADR / 'artifacts/implementation-plan.json'
    require(plan.is_file(), 'preimplementation plan required')
    criteria = manifest['design']['criteria_record']
    require(ROOT / criteria['path'] == plan and sha(plan) == criteria['sha256'], 'plan hash mismatch')
    protected = {str(p.relative_to(ROOT)): sha(p) for p in (
        manifest_path, ADR / 'claim.json', plan, parent_path, relation_path,
        BASE / 'candidate.json', ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json', ROOT / POLICY)}
    base_root, expected = frozen()
    policy = read(base_root / POLICY)
    require(policy.get('max_output_tokens') is None and policy.get('http_retries') == 0
        and policy.get('fallback_allowed') is False and not policy.get('provider_failover'),
        'source policy is not strict and output-unlimited')
    present = sorted(p for p in expected if (ROOT / p).is_file())
    absent = sorted(set(expected) - set(present))
    require(all(not os.path.lexists(ROOT / p) for p in absent), 'absent upstream path exists')
    created = candidate.snapshot(ADR, DEST.name, present,
        experiment_id=manifest['experiment_id'], arm_id='B2', run_ids=['run-001'])
    require(created == DEST, 'unexpected official candidate path')
    for relative in sorted(expected):
        target = DEST / 'snapshot' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base_root / relative, target)
    require(files(DEST / 'snapshot') == expected, 'copy differs from frozen source map')
    require(read(DEST / 'candidate.json')['revisions'] == [], 'candidate unexpectedly frozen')
    frozen()
    require(all(sha(ROOT / p) == h for p,h in protected.items()), 'protected artifact changed')
    print(json.dumps({'status':'PREPARED_UNREGISTERED_UNFROZEN',
        'snapshot_path':str((DEST / 'snapshot').relative_to(ROOT)), 'file_count':len(expected),
        'candidate_manifest_sha256':sha(DEST / 'candidate.json'),
        'source_revision_sha256':BASE_HASH, 'strict_policy_sha256':expected[POLICY],
        'unregistered_absent_files':absent,
        'file_map_sha256':candidate.canonical_sha256(expected),
        'register_executed':False, 'freeze_executed':False,
        'old_candidate_unchanged':True, 'main_unchanged':True,
        'model_calls':0, 'corpus_reads':0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
