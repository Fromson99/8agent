"""ADR1081 explicit immutable inputs and append-only evidence helpers."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-1081-reference-visibility-valid-fixtures'
DESIGN = ADR/'artifacts/design'
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1081/reference-point-r1'
TARGETS = ['02_BACKEND/semantic_runtime/legal_agent/connection_scope.py',
           '02_BACKEND/semantic_runtime/legal_agent/unit_relations.py',
           '02_BACKEND/semantic_runtime/search_selection.py']
SQL_TARGET = '02_BACKEND/semantic_runtime/search_selection.py'


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
