from pathlib import Path
import hashlib, json, sys, gzip
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1285-scenario-review-scope-contract'
ART = ADR / 'artifacts'
DES = ART / 'design'
sys.path.insert(0, str(ROOT / '06_TOOLS/maintenance'))
from experiment_json import write_summary

def read(p):
    p = Path(p)
    with (gzip.open(p, 'rt') if p.suffix == '.gz' else p.open()) as stream:
        return json.load(stream)

def sha(p):
    with Path(p).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def bind(p):
    return {'path': str(Path(p).relative_to(ROOT)), 'sha256': sha(p)}

def put(p, value):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    if p != ADR / '실험/manifest.json':
        return write_summary(p, value)
    with p.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
