import sys
sys.dont_write_bytecode = True
from pathlib import Path
import hashlib, json, gzip
ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1300-connected-law-genos-source-display'
ART = ADR / 'artifacts'
DES = ART / 'design'
sys.path.insert(0, str(ROOT / '06_TOOLS/maintenance'))
from experiment_json import write_summary, write_raw_json

def read(p):
    p = Path(p)
    if not p.is_absolute(): p = ROOT / p
    with (gzip.open(p, 'rt') if p.suffix == '.gz' else p.open()) as stream:
        value = json.load(stream)
    if isinstance(value, dict) and set(value) == {'raw_json'}:
        return read(value['raw_json']['path'])
    return value

def sha(p):
    with Path(p).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def put(p, value):
    p = Path(p)
    if p == ADR / '실험/manifest.json':
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    else: write_summary(p, value)

def raw(p, value):
    ref = write_raw_json(p, value)
    write_summary(Path(str(p) + '.ref.json'), ref)
    return ref
