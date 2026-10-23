from pathlib import Path
import hashlib, json
ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0991-bounded-expansion-retry-two'
ART = ADR / 'artifacts'
def read(p): return json.loads(Path(p).read_text())
def save(p, value):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
def sha(p):
    with Path(p).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
