"""Pin, register and freeze this audit-only continuation; never select it."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1046-ontology-mvp-shared-io'
ART = ADR/'artifacts'
TARGET = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1046/shared-io-r9'
sys.path.insert(0, str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as candidates


def read(path): return json.loads(path.read_text())
def save(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def refresh():
    root = TARGET/'snapshot'
    registered = {row['target_path'] for row in read(TARGET/'candidate.json')['files']}
    for path in sorted(root.rglob('*')):
        if not path.is_file(): continue
        name = str(path.relative_to(root))
        assert '__pycache__' not in name and '.pytest_cache' not in name
        if name not in registered:
            assert not (ROOT/name).exists(), name
            candidates.register_file(TARGET, name, upstream_state='absent')
    additions = ['02_BACKEND/semantic_runtime/legal_agent/'+name for name in (
        'shared_input_values.py', 'input_guidance.py', 'judgment_text_reuse.py')]
    changed = []
    for path in sorted((root/'02_BACKEND/ENGINES').rglob('*.json')):
        value = read(path); files = value.get('files')
        if not isinstance(files, dict): continue
        before = sha(path)
        if any(name.endswith('legal_agent/gateway.py') for name in files):
            files.update({name:sha(root/name) for name in additions})
        for name in files: files[name] = sha(root/name)
        value['files'] = dict(sorted(files.items())); save(path, value)
        if sha(path) != before: changed.append(str(path.relative_to(root)))
    pipeline = read(root/'00_SYSTEM/PIPELINE.json')
    for engine in pipeline['engines'].values():
        engine['sha256'] = sha(root/engine['manifest'])
    def visit(value):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                if key.endswith('_path') and isinstance(item, str):
                    hkey = key[:-5]+'_sha256'
                    if hkey in value and (root/item).is_file(): value[hkey] = sha(root/item)
                visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    visit(pipeline); save(root/'00_SYSTEM/PIPELINE.json', pipeline)
    candidates.refresh(TARGET)
    errors = candidates.validate(TARGET)
    assert errors in ([], ['frozen revision required']), errors
    save(ART/'candidate-registration.json', {'candidate':str(TARGET.relative_to(ROOT)),
        'files':len(read(TARGET/'candidate.json')['files']), 'engine_pins_updated':changed,
        'validation_pending':errors, 'model_calls':0, 'production_loadable':False})


def freeze():
    candidates.freeze(TARGET)
    assert not candidates.validate(TARGET)
    frozen = TARGET/'revisions/rev-001/snapshot'
    tested = read(ART/'contracts-api-summary.json')
    assert tested['status'] == 0 and not tested['candidate_changed_during_tests']
    assert tested['files'] == {str(p.relative_to(frozen)):sha(p)
        for p in frozen.rglob('*') if p.is_file()}, 'frozen code differs from tested code'
    save(ART/'tested-freeze.json', {'candidate':str(TARGET.relative_to(ROOT)),
        'frozen_root':str(frozen.relative_to(ROOT)), 'files':len(tested['files']),
        'test_summary_sha256':sha(ART/'contracts-api-summary.json'),
        'exact_tested_files':True, 'external_model_calls':0, 'real_source_database_opened':False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['refresh', 'freeze'])
    action = parser.parse_args().action
    globals()[action]()
    print(action, 'complete')
