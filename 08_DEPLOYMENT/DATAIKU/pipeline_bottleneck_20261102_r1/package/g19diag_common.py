"""Bounded metadata and exact installed-package binding. No loader state writes."""
import hashlib
import json
from pathlib import Path
import re
import tempfile


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read(path, limit=32*1024**2):
    path = Path(path)
    before = path.stat()
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    after = path.stat()
    if len(raw) > limit or (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('METADATA_LIMIT_OR_CHANGED')
    return json.loads(raw)


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(canonical(value), encoding='utf-8')
    temp.replace(path)


def error(exc):
    return {'type': type(exc).__name__, 'codes': sorted(set(re.findall(r'(?:ORA|PLS)-\d{5}', str(exc))))[:12]}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError('IDENTIFIER')
    return value


def literal(value):
    if not isinstance(value, str) or len(value) > 512 or '\0' in value:
        raise ValueError('LITERAL')
    return "'"+value.replace("'", "''")+"'"


def default_job():
    return Path(tempfile.gettempdir())/'legal-existing-nfs-20261029-r1'/'financial-risk-success-20261005-schema-r2'/'oracle-import-r2'


def context(old_job='', state_dir='', package_dir=''):
    job = Path(old_job or default_job()).resolve(strict=True)
    desc = read(job/'projection-descriptor-r7.json')
    body = {k: v for k, v in desc.items() if k != 'checksum'}
    if digest(body) != desc.get('checksum'):
        raise ValueError('DESCRIPTOR_CHECKSUM')
    full = read(job/'full-state.json')
    matches = []
    candidates = [Path(state_dir)] if state_dir else list(job.parent.glob('gold-shape-*'))[:32]
    for directory in candidates:
        if not (directory/'state.json').is_file():
            continue
        state = read(directory/'state.json')
        binding = state.get('binding', {})
        if binding.get('source_release') == body['binding']['source'] and binding.get('files') == body['binding']['files']:
            matches.append((directory.resolve(), state))
    if len(matches) != 1:
        raise ValueError('STATE_MATCH_REQUIRED_SET_STATE_DIR')
    directory, state = matches[0]
    root = Path(state['binding']['generation']).resolve(strict=True)
    if root != Path(full['identity']['generation']).resolve(strict=True) or job.parent not in root.parents:
        raise ValueError('GENERATION_BINDING')
    manifest = read(root/'manifest.json')
    if hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest() != state['binding']['files']['manifest.json']:
        raise ValueError('SOURCE_MANIFEST_HASH')
    found = []
    packages = [Path(package_dir)] if package_dir else list(Path(tempfile.gettempdir()).glob('legal-gold-fresh-1-*'))[:32]
    for package in packages:
        if not (package/'CODE_MANIFEST.json').is_file():
            continue
        code = read(package/'CODE_MANIFEST.json')
        if digest(code) == state['binding']['code']:
            found.append(package.resolve())
    if len(found) != 1:
        raise ValueError('PACKAGE_MATCH_REQUIRED_SET_PACKAGE_DIR')
    package = found[0]
    code = read(package/'CODE_MANIFEST.json')
    for relative, sha in code['files'].items():
        path = (package/relative).resolve(strict=True)
        if package not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError('INSTALLED_PACKAGE_HASH')
    contract = read(package/'contract.json')
    if digest(contract) != state['binding']['contract']:
        raise ValueError('CONTRACT_BINDING')
    if len(contract['tables']) != 17 or any(not t['name'].endswith('_1') or t['owner'] not in ('SIDDS', 'SIDDA') for t in contract['tables'].values()):
        raise ValueError('FRESH_1_TARGET_REQUIRED')
    for t in contract['tables'].values():
        identifier(t['owner']); identifier(t['name'])
        for c in t['columns'].values(): identifier(c['name'])
    return {'job': str(job), 'state_dir': str(directory), 'package': str(package), 'root': str(root),
            'descriptor': body, 'descriptor_checksum': desc['checksum'], 'state': state,
            'manifest': manifest, 'contract': contract,
            'scope': 'metadata binding verified; full SQLite file hashes not reread by snapshot'}
