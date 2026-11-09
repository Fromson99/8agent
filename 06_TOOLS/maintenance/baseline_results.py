"""Per-file test results of an exact code tree, kept so the next MAIN does not rerun the old one.

A code tree is identified by its inventory hash: SHA-256 over the sorted
{relative path: file SHA-256} of every file in it (``__pycache__``/``.pyc``
excluded).  A staged candidate and the release prepared from it have the same
inventory, so the candidate's own run becomes the baseline once it is selected
as MAIN.

One entry per (inventory, test file).  An entry is reused only while the test
file and the test harness (05_TESTS/conftest.py, pytest_code_root.py) still
have the recorded hashes; any other change (fixtures, tool modules, data) can
still make a cached result stale, which is why main_release.py reruns every
test whose outcome differs, alone, on both trees before calling it new.

Entries live in 90_RUNTIME/TEST_BASELINES/<inventory sha>/ and can be deleted
at any time; they are only a cache.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / '90_RUNTIME' / 'TEST_BASELINES'
HARNESS = (ROOT / '05_TESTS' / 'conftest.py', ROOT / '06_TOOLS' / 'maintenance' / 'pytest_code_root.py')


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(code_root: Path) -> dict[str, str]:
    code_root = Path(code_root).resolve()
    files = {}
    for directory, names, filenames in os.walk(code_root):
        names[:] = sorted(name for name in names if name != '__pycache__')
        for filename in filenames:
            if filename.endswith('.pyc'):
                continue
            path = Path(directory) / filename
            files[path.relative_to(code_root).as_posix()] = sha_file(path)
    return dict(sorted(files.items()))


def inventory_sha(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(dict(sorted(files.items())), separators=(',', ':')).encode()).hexdigest()


def harness_sha() -> str:
    return hashlib.sha256(''.join(sha_file(path) for path in HARNESS).encode()).hexdigest()


def _entry_path(inventory_hash: str, test_file: str) -> Path:
    return STORE / inventory_hash / (test_file.replace('/', '__') + '.json')


def save(inventory_hash: str, code_root: Path, test_file: str, tests: list[dict]) -> None:
    path = _entry_path(inventory_hash, test_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {'schema_version': 'test-baseline-v1', 'inventory_sha256': inventory_hash, 'code_root': str(code_root),
             'test_file': test_file, 'test_sha256': sha_file(ROOT / test_file), 'harness_sha256': harness_sha(),
             'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'tests': tests}
    temporary = path.with_name('.' + path.name + f'.{os.getpid()}')
    temporary.write_text(json.dumps(entry, ensure_ascii=False, indent=1) + '\n')
    os.replace(temporary, path)


def load(inventory_hash: str, test_file: str) -> dict | None:
    """The cached entry, or None when missing or recorded with another test file or harness."""
    path = _entry_path(inventory_hash, test_file)
    try:
        entry = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return None
    if entry.get('test_sha256') != sha_file(ROOT / test_file) or entry.get('harness_sha256') != harness_sha():
        return None
    return entry


def save_result(result: dict) -> int:
    """Store every completely finished file of a run_tests.py --code-root result; returns the count."""
    unfinished = {name for batch in result['incomplete_batches'] for name in batch['files']}
    by_file = {}
    for test in result['tests']:
        by_file.setdefault(test['nodeid'].split('::')[0], []).append(test)
    saved = 0
    for test_file in result['files']:
        if test_file in unfinished or test_file in result.get('isolation_violation_files', []):
            continue
        save(result['code_inventory_sha256'], Path(result['code_root']), test_file, by_file.get(test_file, []))
        saved += 1
    return saved
