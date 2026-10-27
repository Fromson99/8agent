"""ADR1078 append-only artifacts and explicit selected-MAIN provenance."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1078-navigation-bound-replay'
DESIGN = ADR/'artifacts/design'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1078/view-preparation-r1'
TARGETS = ['02_BACKEND/semantic_runtime/legal_agent/connection_scope.py',
           '02_BACKEND/semantic_runtime/legal_agent/unit_relations.py']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def put(path,value,*,replace=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w' if replace else 'x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.write('\n')


def bound(path):
    return {'path':str(path.relative_to(ROOT)),'sha256':sha(path)}
