"""Create a fresh isolated compiler candidate after baseline pin maintenance.

No model calls, source-data copies, default activation or approval changes.
The original working candidate and its recorded provenance remain untouched.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '06_TOOLS/COMMANDS'))
import adr_candidate as candidates

ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1041-ontology-mvp-37-compiler'
ORIGINAL = ROOT / '02_BACKEND/lawrag/research/candidates/adr_1041/compiler'
OVERLAYS = [
    '02_BACKEND/semantic_runtime/legal_agent/law_candidates.py',
    '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py',
    '02_BACKEND/semantic_runtime/legal_agent/decision_projection.py',
    '02_BACKEND/semantic_runtime/legal_agent/unit_relations.py',
]
NEW = [
    '02_BACKEND/semantic_runtime/legal_agent/ontology_compiler.py',
    '02_BACKEND/semantic_runtime/legal_agent/ontology_context.py',
    '00_SYSTEM/SCHEMAS/ontology-bundle-v0.schema.json',
    '05_TESTS/CONTRACTS/test_ontology_compiler.py',
    '05_TESTS/CONTRACTS/test_ontology_context.py',
    '05_TESTS/CONTRACTS/test_ontology_api.py',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def dependencies(origin):
    """Follow test-helper imports only; no entire test-tree snapshot."""
    test_root = ROOT / '05_TESTS/CONTRACTS'
    pending = [origin / 'snapshot' / name for name in NEW if name.endswith('.py')]
    selected = {'05_TESTS/conftest.py'}
    while pending:
        path = pending.pop()
        for node in ast.walk(ast.parse(path.read_text())):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                if not module or not module.startswith('test_'):
                    continue
                helper = test_root / (module.split('.')[0] + '.py')
                relative = helper.relative_to(ROOT).as_posix()
                if helper.is_file() and relative not in selected:
                    selected.add(relative)
                    pending.append(helper)
    return selected


def repin(root):
    """Bind all copied engine declarations to exactly this candidate code."""
    additions = NEW[:3]
    changed = []
    for path in sorted((root / '02_BACKEND/ENGINES').rglob('*.json')):
        manifest = json.loads(path.read_text())
        files = manifest.get('files')
        if not isinstance(files, dict):
            continue
        before = sha(path)
        if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in files:
            files.update({name: sha(root / name) for name in additions})
        for name in files:
            if not (root / name).is_file():
                raise ValueError('engine dependency missing from snapshot: ' + name)
            files[name] = sha(root / name)
        manifest['files'] = dict(sorted(files.items()))
        write(path, manifest)
        if before != sha(path):
            changed.append(path.relative_to(root).as_posix())
    path = root / '00_SYSTEM/PIPELINE.json'
    pipeline = json.loads(path.read_text())
    for entry in pipeline['engines'].values():
        entry['sha256'] = sha(root / entry['manifest'])
    def visit(value):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                if key.endswith('_path') and isinstance(item, str):
                    hash_key = key[:-5] + '_sha256'
                    if hash_key in value and (root / item).is_file():
                        value[hash_key] = sha(root / item)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(pipeline)
    write(path, pipeline)
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate-id', required=True)
    parser.add_argument('--source-candidate', default='compiler-r3')
    args = parser.parse_args()
    if not candidates.ID_RE.fullmatch(args.source_candidate):
        raise ValueError('source candidate must be a registered candidate name')
    origin = ORIGINAL.parent / args.source_candidate
    original = json.loads((origin / 'candidate.json').read_text())
    if original['adr_id'] != 'ADR-1041':
        raise ValueError('wrong source ADR')
    sources = {r['target_path'] for r in original['files'] if r['upstream_state'] == 'present'}
    for name in list(sources):
        if name.startswith('02_BACKEND/ENGINES/') and name.endswith('.json'):
            sources.update(json.loads((ROOT / name).read_text()).get('files', {}))
    sources.update(dependencies(origin))
    sources.update(['06_TOOLS/EXPERIMENTS/adr_1041/stage_candidate.py',
                    '06_TOOLS/EXPERIMENTS/adr_1041/prepare_seeds.py'])
    target = candidates.snapshot(ADR, args.candidate_id, sorted(sources),
        experiment_id='ADR-1041-experiment-v1', arm_id='A2', run_ids=['run-001'])
    root = target / 'snapshot'
    for name in OVERLAYS + NEW:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin / 'snapshot' / name, path)
        if name in NEW:
            candidates.register_file(target, target=name, upstream_state='absent')
    engines = repin(root)
    candidates.refresh(target)
    candidates.freeze(target)
    errors = candidates.validate(target)
    if errors:
        raise ValueError(errors)
    report = {'candidate_dir': str(target.relative_to(ROOT)),
              'root': str(root.relative_to(ROOT)),
              'frozen_root': str((target / 'revisions/rev-001/snapshot').relative_to(ROOT)),
              'candidate_manifest_sha256': sha(target / 'candidate.json'),
              'base_pointer_sha256': sha(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
              'origin': str(origin.relative_to(ROOT)), 'overlays': OVERLAYS,
              'new_files': NEW, 'test_helper_files': sorted(dependencies(origin)),
              'repinned_engines': engines, 'live_model_calls': 0,
              'seed_approval': 'PENDING', 'production_loadable': False}
    write(ADR / 'artifacts' / (args.candidate_id + '-stage.json'), report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
