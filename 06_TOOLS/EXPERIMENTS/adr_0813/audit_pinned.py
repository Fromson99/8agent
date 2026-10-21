from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0813-evidence-first-comparison'
f=json.loads((A/'artifacts/design/freeze.json').read_text())
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in f['files'].items())
print('PASS frozen candidate')
