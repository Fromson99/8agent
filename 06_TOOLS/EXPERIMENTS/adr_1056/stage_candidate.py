"""Pin, register and freeze this audit-only continuation; never select it."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1056-grouped-fulltext-compact-laws'
ART = ADR/'artifacts'
TARGET = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1056/grouped-query-r1'
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
        'read_judgment_repair.py', 'step_state.py', 'law_overview.py', 'shared_input_values.py', 'input_guidance.py', 'judgment_text_reuse.py',
        'model_input_projection.py', 'read_connection_guidance.py')]
    changed = []
    for path in sorted((root/'02_BACKEND/ENGINES').rglob('*.json')):
        value = read(path); files = value.get('files')
        if not isinstance(files, dict): continue
        before = sha(path)
        if any(name.endswith('legal_agent/gateway.py') for name in files):
            files.update({name:sha(root/name) for name in additions})
            files['02_BACKEND/semantic_runtime/fulltext_query.py']=sha(root/'02_BACKEND/semantic_runtime/fulltext_query.py')
            files['02_BACKEND/semantic_runtime/legal_agent/law_choice_projection.py']=sha(root/'02_BACKEND/semantic_runtime/legal_agent/law_choice_projection.py')
        if any(name.endswith('research/experiment_client.py') for name in files):
            files['02_BACKEND/lawrag/research/provider_failover.py'] = sha(root/'02_BACKEND/lawrag/research/provider_failover.py')
        for name in files: files[name] = sha(root/name)
        value['files'] = dict(sorted(files.items())); save(path, value)
        if sha(path) != before: changed.append(str(path.relative_to(root)))
    pipeline = read(root/'00_SYSTEM/PIPELINE.json')
    for engine in pipeline['engines'].values():
        engine['sha256'] = sha(root/engine['manifest'])
    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'),str) and 'sha256' in value and (root/value['path']).is_file():
                value['sha256']=sha(root/value['path'])
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


if __name__ == "__main__":
    refresh()
