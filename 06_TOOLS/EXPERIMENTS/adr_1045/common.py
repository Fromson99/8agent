"""Small shared I/O helpers for the isolated, sequential MVP experiment."""
from pathlib import Path
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-1045-ontology-mvp-terminal-frame'
ART = ADR / 'artifacts'
RESPONSE_RECEPTION = 'buffered-json-sse-v1'
WHITESPACE_LIMIT = 8192


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    """Atomically replace this run's mutable receipt; never use on frozen inputs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def exact_write(path, value):
    """Create immutable input once; identical reruns are safe, drift is refused."""
    path = Path(path)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('existing input differs: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
