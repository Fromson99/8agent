"""Update only this task's changed sources; verify all existing engine pins."""
import hashlib
import json
from pathlib import Path

from common import ROOT as WORKSPACE, ART, read
import sys
ROOT = Path(sys.argv[1]) if len(sys.argv)>1 else WORKSPACE/read(ART/'stage.json')['roots']['candidate']
OUT = ART


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


changed = ['02_BACKEND/semantic_runtime/legal_agent/' + n for n in
           ('connection_scope.py', 'decision_projection.py')]
changed.append('00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
pins = {}
for path in (ROOT / '02_BACKEND/ENGINES').rglob('*.json'):
    value = json.loads(path.read_text())
    if 'files' not in value:
        continue
    before = sha(path)
    for name in changed:
        if name in value['files']:
            value['files'][name] = sha(ROOT / name)
    # Preserve bytes in unaffected manifests.
    if value != json.loads(path.read_text()):
        save(path, value)
        pins[str(path.relative_to(ROOT))] = {'before': before, 'after': sha(path)}
path = ROOT / '00_SYSTEM/PIPELINE.json'
value = json.loads(path.read_text()); before = sha(path)
for engine in value['engines'].values():
    if engine['manifest'] in pins:
        engine['sha256'] = sha(ROOT / engine['manifest'])
if value != json.loads(path.read_text()):
    save(path, value)
    pins[str(path.relative_to(ROOT))] = {'before': before, 'after': sha(path)}
checked = 0
for path in (ROOT / '02_BACKEND/ENGINES').rglob('*.json'):
    for name, expected in json.loads(path.read_text()).get('files', {}).items():
        assert sha(ROOT / name) == expected, name
        checked += 1
for engine in value['engines'].values():
    assert sha(ROOT / engine['manifest']) == engine['sha256']
save(OUT / ('working-pins.json' if ROOT==WORKSPACE else 'candidate-pins.json'), {'checked': checked, 'changes': pins})
print('Verified', checked, 'file pins;', len(value['engines']), 'manifest pins')
