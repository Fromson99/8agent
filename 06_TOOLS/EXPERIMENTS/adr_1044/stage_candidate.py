"""Register the prepared response-reception candidate using the stable lifecycle.

The draft came from the exact ADR1043 frozen file map. No source corpus or
runtime is copied, no model is invoked, and no active selector is changed.
"""
from pathlib import Path
import argparse
import json
import shutil
import sys
from common import ROOT, ADR, ART, read, save, sha

sys.path.insert(0, str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as candidates

BASE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1044'
TARGET = BASE/'compiler-r7'


def repin(root):
    additions = ['02_BACKEND/semantic_runtime/legal_agent/'+name for name in (
        'buffered_json_stream.py', 'buffered_external_transport.py', 'output_key_aliases.py')]
    changed = []
    for path in sorted((root/'02_BACKEND/ENGINES').rglob('*.json')):
        value = read(path); files = value.get('files')
        if not isinstance(files, dict):
            continue
        before = sha(path)
        if any('legal_agent/'+n in '\n'.join(files) for n in ('gateway.py', 'local_gemma.py')):
            files.update({name:sha(root/name) for name in additions})
        for name in files:
            files[name] = sha(root/name)
        value['files'] = dict(sorted(files.items())); save(path, value)
        if sha(path) != before: changed.append(str(path.relative_to(root)))
    pipeline = read(root/'00_SYSTEM/PIPELINE.json')
    for engine in pipeline['engines'].values():
        engine['sha256'] = sha(root/engine['manifest'])
    def visit(value):
        if isinstance(value, dict):
            for key, item in list(value.items()):
                if key.endswith('_path') and isinstance(item, str):
                    hash_key = key[:-5]+'_sha256'
                    if hash_key in value and (root/item).is_file():
                        value[hash_key] = sha(root/item)
                visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    visit(pipeline); save(root/'00_SYSTEM/PIPELINE.json', pipeline)
    return changed


def prepare():
    assert not (TARGET/'candidate.json').exists()
    stage = BASE/'compiler-r7-pre-registration'
    assert not stage.exists()
    files = {str(p.relative_to(TARGET/'snapshot')):sha(p)
             for p in (TARGET/'snapshot').rglob('*') if p.is_file()}
    assert files and not any('__pycache__' in p for p in files)
    TARGET.rename(stage)
    present = sorted(p for p in files if (ROOT/p).is_file())
    candidates.snapshot(ADR, 'compiler-r7', present,
        experiment_id='ADR-1044-experiment-v1', arm_id='A2', run_ids=['run-001'])
    for name, expected in files.items():
        source = stage/'snapshot'/name; assert sha(source) == expected
        dest = TARGET/'snapshot'/name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        if name not in present:
            candidates.register_file(TARGET, name, upstream_state='absent')
    assert all(sha(TARGET/'snapshot'/p) == h for p,h in files.items())
    # Only the verified temporary duplicate created in this function is removed.
    shutil.rmtree(stage)
    refresh()


def refresh():
    changed = repin(TARGET/'snapshot')
    candidates.refresh(TARGET)
    errors = candidates.validate(TARGET)
    assert errors in ([], ['frozen revision required']), errors
    save(ART/'candidate-registration.json', {'candidate':str(TARGET.relative_to(ROOT)),
        'files':len(read(TARGET/'candidate.json')['files']),
        'engine_pins_updated':changed, 'validation_pending':errors,
        'model_calls':0, 'production_loadable':False})


def freeze():
    candidates.freeze(TARGET)
    assert not candidates.validate(TARGET)
    original = read(TARGET/'candidate.json')
    present = [r['target_path'] for r in original['files'] if (ROOT/r['target_path']).is_file()]
    second = candidates.snapshot(ADR, 'compiler-a1-r7', present,
        experiment_id='ADR-1044-experiment-v1', arm_id='A1', run_ids=['run-001'])
    for row in original['files']:
        name = row['target_path']; dest = second/'snapshot'/name
        source = TARGET/'revisions/rev-001/snapshot'/name
        assert sha(source) == row['snapshot_sha256']
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source,dest)
        if name not in present: candidates.register_file(second,name,upstream_state='absent')
    candidates.refresh(second); candidates.freeze(second)
    assert not candidates.validate(second)
    assert {r['target_path']:r['snapshot_sha256'] for r in original['files']} == {
        r['target_path']:r['snapshot_sha256'] for r in read(second/'candidate.json')['files']}
    save(ART/'identical-arm-code.json', {'a1':str(second.relative_to(ROOT)),
        'a2':str(TARGET.relative_to(ROOT)), 'files':len(original['files']),
        'same_execution_root':str((TARGET/'revisions/rev-001/snapshot').relative_to(ROOT)),
        'model_calls':0, 'production_loadable':False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action',choices=['prepare','refresh','freeze'])
    action = parser.parse_args().action
    globals()[action]()
    print(action, 'complete')
