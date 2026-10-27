"""Prepare ADR1069 B0 without registering new files or freezing a revision.

The exact ADR1066 A0 source receives only the named ADR1068 baseline timing
files and current strict model policy. Product behavior fixes and P1 are absent.
Run stage_candidate only after the profiling implementation is ready.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1069-navigation-view-211s-profile'
BASE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1066/action-choice-a0-r1'
EQUIVALENT = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1066/action-choice-a2-r1'
TIMING = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1068/profile-baseline-r1'
DEST = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1069/profile-baseline-r1'
REVISION = 'rev-001'
BASE_HASH = '2f5ab715b46f2b1732261954f634a035614f8209c10ea82b5e0290b504256c54'
TIMING_HASH = '88f33eeef8f214c6ff8d198e03cee99633af0e2c4697c29ad0fc416bd7cfe2c8'
TIMING_FILES = (
    'genos_timing_probe.py',
    '02_BACKEND/semantic_runtime/document_agent.py',
    '02_BACKEND/semantic_runtime/legal_agent_adapter.py',
    '02_BACKEND/semantic_runtime/resident_data.py',
    'service.py',
    '02_BACKEND/semantic_runtime/query_latency.py',
    '02_BACKEND/semantic_runtime/execution_metrics.py',
    '02_BACKEND/semantic_runtime/request_report.py',
)
POLICY = '00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'
GRANT = '00_SYSTEM/LEGAL_AGENT/local-gemma-public.json'
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
        if path.is_file(): result[path.relative_to(root).as_posix()] = sha(path)
        else: require(path.is_dir(), 'special file in snapshot')
    return result


def frozen(directory, expected_hash=None):
    manifest = read(directory / 'candidate.json')
    revision = next(r for r in manifest['revisions'] if r['revision_id'] == REVISION)
    actual_hash = candidate.canonical_sha256({k:v for k,v in revision.items() if k != 'revision_sha256'})
    require(actual_hash == revision['revision_sha256'], 'source revision metadata changed')
    require(expected_hash is None or actual_hash == expected_hash, 'wrong source revision')
    root = directory / 'revisions' / REVISION / 'snapshot'
    expected = {}
    for row in revision['files']:
        path = ROOT / row['frozen_path']
        require(path.resolve().is_relative_to(root.resolve()), 'source path escapes revision')
        relative = path.relative_to(root).as_posix()
        require(relative not in expected, 'duplicate source path')
        expected[relative] = row['snapshot_sha256']
    require(files(root) == expected, 'source file inventory changed')
    return root, expected


def main():
    require(not DEST.exists(), 'candidate exists; never overwrite or silently resume')
    manifest_path = ADR / '실험/manifest.json'
    manifest = read(manifest_path)
    require(manifest['experiment_id'] == 'ADR-1069-experiment-v1'
        and manifest['reservation']['status'] == 'in_progress', 'incorrect or inactive ADR')
    parents = manifest['lineage']['parents']
    require(len(parents) == 1 and parents[0]['experiment_id'] == 'ADR-1065-experiment-v1'
        and parents[0]['arm_id'] == 'A2', 'wrong parent')
    parent_path = ROOT / parents[0]['manifest_path']
    require(sha(parent_path) == parents[0]['manifest_sha256'], 'parent manifest changed')
    parent = read(parent_path)
    require(parent['reservation']['status'] == 'completed'
        and parent['results']['by_arm']['A2']['status'] == 'complete', 'parent is incomplete')
    protected = {str(p.relative_to(ROOT)): sha(p) for p in (
        manifest_path, ADR / 'claim.json', parent_path, BASE / 'candidate.json',
        EQUIVALENT / 'candidate.json', TIMING / 'candidate.json',
        ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json', ROOT / POLICY)}
    plan = ADR / 'artifacts/implementation-plan.json'
    if plan.exists(): protected[str(plan.relative_to(ROOT))] = sha(plan)
    base_root, base_files = frozen(BASE, BASE_HASH)
    _, equivalent_files = frozen(EQUIVALENT)
    require(len(base_files) == 743 and base_files == equivalent_files, 'A0/A2 code maps differ')
    timing_root, timing_files = frozen(TIMING, TIMING_HASH)
    expected = dict(base_files)
    expected.update({path: timing_files[path] for path in TIMING_FILES})
    present = sorted(p for p in expected if (ROOT / p).is_file())
    absent = sorted(set(expected) - set(present))
    require(all(not os.path.lexists(ROOT / p) for p in absent), 'absent upstream path exists')
    created = candidate.snapshot(ADR, DEST.name, present,
        experiment_id=manifest['experiment_id'], arm_id='B0', run_ids=['run-001'])
    require(created == DEST, 'unexpected official candidate path')
    for relative in sorted(expected):
        target = DEST / 'snapshot' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2((timing_root if relative in TIMING_FILES else base_root) / relative, target)
    require(files(DEST / 'snapshot') == expected, 'overlay differs from declared source map')
    policy = read(ROOT / POLICY)
    require(policy.get('max_output_tokens') is None and policy.get('http_retries') == 0
        and policy.get('fallback_allowed') is False and not policy.get('provider_failover'),
        'current policy is not strict and output-unlimited')
    shutil.copy2(ROOT / POLICY, DEST / 'snapshot' / POLICY)
    grant_path = DEST / 'snapshot' / GRANT
    grant = read(grant_path); grant['policy_sha256'] = sha(DEST / 'snapshot' / POLICY)
    grant_path.write_text(json.dumps(grant, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    expected[POLICY] = sha(DEST / 'snapshot' / POLICY)
    expected[GRANT] = sha(grant_path)
    require(files(DEST / 'snapshot') == expected, 'unexpected candidate change')
    require(read(DEST / 'candidate.json')['revisions'] == [], 'candidate unexpectedly frozen')
    frozen(BASE, BASE_HASH); frozen(EQUIVALENT); frozen(TIMING, TIMING_HASH)
    require(all(sha(ROOT / p) == h for p,h in protected.items()), 'protected artifact changed')
    print(json.dumps({'status':'PREPARED_UNREGISTERED_UNFROZEN',
        'snapshot_path':str((DEST / 'snapshot').relative_to(ROOT)), 'file_count':len(expected),
        'candidate_manifest_sha256':sha(DEST / 'candidate.json'),
        'source_revision_sha256':BASE_HASH, 'timing_revision_sha256':TIMING_HASH,
        'timing_overlays':{p:timing_files[p] for p in TIMING_FILES},
        'strict_policy_sha256':expected[POLICY], 'unregistered_absent_files':absent,
        'file_map_sha256':candidate.canonical_sha256(expected),
        'register_executed':False, 'freeze_executed':False,
        'old_candidates_unchanged':True, 'main_unchanged':True,
        'model_calls':0, 'corpus_reads':0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
