"""Accept Oracle navigation rows built by loader code with proven-identical output.

The Dataiku loader records, in the query release manifest, the sha256 of the
navigation compiler files it ran ('navigation_compilers'). Serving reads those
rows with its own copies of the same files. Lookup keys are digests of text
normalized by these files, so rows from a different derivation would not fail:
lookups would silently return nothing. Identical bytes are therefore always
accepted, and different bytes only when both versions sit in the same group of
00_SYSTEM/ORACLE/navigation_compatibility.json. A group lists code versions for
which 06_TOOLS/maintenance/navigation_compatibility.py ran the real publisher
over the reference generation and obtained the same rows (the fingerprint).
Edits that do not change the derivation (refactors, new query-time methods)
are registered there before release; edits that change it need a republish.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import importlib
import json
from pathlib import Path
import re

from .oracle_dp_io import DPError

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = '00_SYSTEM/ORACLE/navigation_compatibility.json'
SCHEMA = 'navigation-compatibility-v1'
MODULES = {
    'semantic_runtime.navigation_match': '02_BACKEND/semantic_runtime/navigation_match.py',
    'semantic_runtime.structure_navigation': '02_BACKEND/semantic_runtime/structure_navigation.py',
    'semantic_runtime.inherited_navigation': '02_BACKEND/semantic_runtime/inherited_navigation.py',
}
_SHA = re.compile('[0-9a-f]{64}')
TOOL = '06_TOOLS/maintenance/navigation_compatibility.py register'


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def current():
    """Hashes of the compiler files this process actually imported."""
    return {name: file_sha(importlib.import_module(name).__file__) for name in MODULES}


def validate(value):
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA or value.get('modules') != MODULES:
        raise DPError('QUERY_STRUCTURE_COMPILER: invalid navigation compatibility registry')
    seen = {}
    groups = value.get('groups')
    if not isinstance(groups, list) or not groups:
        raise DPError('QUERY_STRUCTURE_COMPILER: empty navigation compatibility registry')
    for group in groups:
        fingerprint = group.get('fingerprint') if isinstance(group, dict) else None
        versions = group.get('versions') if isinstance(group, dict) else None
        if not isinstance(fingerprint, str) or not _SHA.fullmatch(fingerprint) or not isinstance(versions, list) or not versions:
            raise DPError('QUERY_STRUCTURE_COMPILER: invalid navigation compatibility group')
        for version in versions:
            modules = version.get('modules') if isinstance(version, dict) else None
            if (not isinstance(modules, dict) or set(modules) != set(MODULES) or
                    not all(isinstance(v, str) and _SHA.fullmatch(v) for v in modules.values())):
                raise DPError('QUERY_STRUCTURE_COMPILER: invalid navigation compatibility version')
            key = tuple(modules[name] for name in MODULES)
            if seen.setdefault(key, fingerprint) != fingerprint:
                raise DPError('QUERY_STRUCTURE_COMPILER: one code version listed in two groups')
    return {key: fingerprint for key, fingerprint in seen.items()}


@lru_cache(maxsize=4)
def _groups(path, sha256):
    with Path(path).open('rb') as stream:
        raw = stream.read()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise DPError('QUERY_STRUCTURE_COMPILER: compatibility registry changed while loading')
    return validate(json.loads(raw))


def groups(root=ROOT):
    path = Path(root) / REGISTRY
    if not path.is_file():
        return None
    return _groups(str(path), file_sha(path))


def _short(version):
    return ','.join(name.rsplit('.', 1)[1] + '=' + str(version[name])[:12] for name in MODULES)


def require(recorded, *, root=ROOT, now=None):
    """Raise unless rows recorded with `recorded` read correctly with this code."""
    recorded = {name: (recorded or {}).get(name) for name in MODULES}
    now = current() if now is None else now
    if recorded == now:
        return {'status': 'EXACT'}
    known = groups(root)
    differs = [name.rsplit('.', 1)[1] for name in MODULES if recorded[name] != now[name]]
    if known is None:
        raise DPError('QUERY_STRUCTURE_COMPILER: republish derived navigation for this code '
                      f'(differs={",".join(differs)}; no compatibility registry)')
    mine = known.get(tuple(now[name] for name in MODULES))
    if mine is None:
        raise DPError('QUERY_STRUCTURE_COMPILER: this serving code version is not registered; '
                      f'run {TOOL} before release (serving {_short(now)})')
    theirs = known.get(tuple(recorded[name] for name in MODULES))
    if theirs != mine:
        raise DPError('QUERY_STRUCTURE_COMPILER: Oracle navigation rows were built by loader code with a different '
                      f'derivation; republish derived navigation for this code (loader {_short(recorded)}; serving {_short(now)})')
    return {'status': 'COMPATIBLE', 'fingerprint': mine, 'differs': differs}
