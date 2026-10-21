"""Verify frozen technical audit outputs without changing any candidate input."""
from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0794-definition-entry-storage-binding';D=A/'artifacts/design'
f=json.loads((D/'freeze.json').read_text())
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in f['files'].items())
s=(A/'artifacts/tests-001.log').read_text();assert re.search(r'\b516 passed\b',s) and 'FAILED ' not in s
receipt=json.loads((A/'artifacts/candidate-consumer-v2.json').read_text());assert all(receipt['checks'].values())
print('PASS: frozen candidate, 516 contract checks and actual service/API consumers')
