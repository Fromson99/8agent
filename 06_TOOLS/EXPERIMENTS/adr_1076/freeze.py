"""Freeze the evaluated MAIN104 derivative and independent finite-census runner."""
from common import *
from datetime import datetime, timezone
import subprocess

assert not (DESIGN/'freeze.json').exists()
assert (ROOT/'06_TOOLS/EXPERIMENTS/adr_1076/finite_runner.py').is_file()
assert (DESIGN/'secondary-replay.json').is_file()
for name in ('native_replay.py', 'native_transport.py', 'native_inventory.py', 'test_native_transport.py'):
    assert (ROOT/'06_TOOLS/EXPERIMENTS/adr_1076'/name).is_file()
manifest = read(ADR/'실험/manifest.json')
assert len(manifest['runs']) == 1 and manifest['runs'][0]['status'] == 'planned'
manifest['runs'].append({'id': 'run-002', 'purpose': 'audit', 'parent_run_id': 'run-001',
    'arm_ids': ['baseline', 'optimized'], 'status': 'planned',
    'selection_rule': 'Known ADR1075 exact38 recorded responses; all35 native frames, sequential arms. Secondary in-sample performance only, never legal holdout.',
    'artifact_path': str((ADR/'artifacts/run-002/result.json').relative_to(ROOT)), 'sha256': 'PENDING'})
manifest['design']['secondary_replay'] = bound(DESIGN/'secondary-replay.json')
put(ADR/'실험/manifest.json', manifest, replace=True)
cm = read(CANDIDATE/'candidate.json')
assert not cm['revisions'] and cm['run_ids'] == ['run-001']
cm['run_ids'] = ['run-001', 'run-002']
cm['updated_at'] = datetime.now(timezone.utc).isoformat()
put(CANDIDATE/'candidate.json', cm, replace=True)
put(DESIGN/'secondary-run-binding.json', {'before_product_execution': True,
    'run_ids': cm['run_ids'], 'candidate': str(CANDIDATE.relative_to(ROOT)),
    'secondary_contract': bound(DESIGN/'secondary-replay.json'),
    'reason': 'The prospective primary design reserved a separate known-trace replay; bind its exact runner and input before either run.'})
base = read(DESIGN/'baseline.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == base['pointer_sha256']
stage = CANDIDATE/'snapshot'
pipeline = read(stage/'00_SYSTEM/PIPELINE.json')
pin_paths = {'00_SYSTEM/PIPELINE.json'}
for engine_ref in pipeline['engines'].values():
    path = stage/engine_ref['manifest']
    engine = read(path)
    changed = False
    for target in TARGETS:
        if target in engine['files']:
            engine['files'][target] = sha(stage/target)
            changed = True
    if changed:
        put(path, engine, replace=True)
        engine_ref['sha256'] = sha(path)
        pin_paths.add(engine_ref['manifest'])
put(stage/'00_SYSTEM/PIPELINE.json', pipeline, replace=True)
changes = [name for name, old in base['manifest']['files'].items() if sha(stage/name) != old]
assert set(changes) <= set(TARGETS) | pin_paths
assert set(TARGETS) <= set(changes)
put(DESIGN/'candidate-preparation.json', {'source_targets': TARGETS, 'pin_paths': sorted(pin_paths),
    'changed': changes, 'serving_files': {name: sha(stage/name) for name in base['manifest']['files']},
    'scope': 'Invocation-local acquired-read preparation only; selected MAIN104 presentation/action policy unchanged.'})
subprocess.run([str(ROOT/'.venv/bin/python'), '06_TOOLS/run_tool.py', 'adr_candidate.py',
    'freeze', str(CANDIDATE)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
cm = read(CANDIDATE/'candidate.json')
revision = cm['revisions'][-1]
code = CANDIDATE/'revisions'/revision['revision_id']/'snapshot'
binding = {'manifest_path': str((CANDIDATE/'candidate.json').relative_to(ROOT)),
    'manifest_sha256': sha(CANDIDATE/'candidate.json'), 'revision_id': revision['revision_id'],
    'revision_sha256': revision['revision_sha256']}
files = {name: sha(code/name) for name in base['manifest']['files']}
reviewed = [{'path': name, 'before': base['manifest']['files'][name], 'after': files[name],
    'reason': 'Successful acquired-read preparation reuse within one menu construction, or its exact dependency hash pin.'}
    for name in sorted(changes)]
rebase = {'schema_version': 'evaluated-release-rebase-v1',
    'base_release_manifest_sha256': base['pointer']['release_manifest_sha256'],
    'candidate': binding, 'staged_files': files, 'excluded_candidate_paths': {},
    'reviewed_changes': reviewed, 'base_code_root': base['manifest']['code_root'],
    'stage': str(code.relative_to(ROOT)),
    'reason': 'Exact selected MAIN104 plus two-module invocation-local preparation; no ontology/task-local/menu/model/profile/data changes.'}
put(DESIGN/'release-rebase.json', rebase)
put(DESIGN/'integration.json', {'schema_version': 'local-release-integration-v1',
    'base_release_manifest_sha256': base['pointer']['release_manifest_sha256'],
    'changes': reviewed, 'candidate': binding, 'rebase_receipt': bound(DESIGN/'release-rebase.json')})
manifest = read(ADR/'실험/manifest.json')
manifest['design']['release_rebase'] = bound(DESIGN/'release-rebase.json')
manifest['design']['code_isolation']['candidates'] = [{**binding,
    'candidate_id': CANDIDATE.name, 'arm_id': 'optimized', 'experiment_id': manifest['experiment_id'],
    'run_ids': ['run-001', 'run-002'], 'runner_path': '06_TOOLS/EXPERIMENTS/adr_1076/audit.py',
    'runner_sha256': sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1076/audit.py')}]
put(ADR/'실험/manifest.json', manifest, replace=True)
frozen = {str(path.relative_to(ROOT)): sha(path)
    for path in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1076').glob('*.py')}
frozen.update({str(path.relative_to(ROOT)): sha(path) for path in DESIGN.glob('*.json')})
frozen.update({str((code/name).relative_to(ROOT)): value for name, value in files.items()})
frozen.update({str((ROOT/base['manifest']['code_root']/name).relative_to(ROOT)): value
    for name, value in base['manifest']['files'].items()})
frozen[str((CANDIDATE/'candidate.json').relative_to(ROOT))] = sha(CANDIDATE/'candidate.json')
put(DESIGN/'freeze.json', {'schema_version': 'adr1076-census-freeze-v1',
    'frozen_at': datetime.now(timezone.utc).isoformat(), 'code_root': str(code.relative_to(ROOT)),
    'files': frozen, 'serving_files': files, 'candidate': binding})
print('Frozen MAIN104 derivative:', len(files), 'serving files;', len(changes), 'changed; model0/corpus0')
