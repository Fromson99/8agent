"""Bounded, read-only GENOS NFS/code-identity diagnostic. Standard library only."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys
import time
import uuid

REVISION = 'nfs-data-probe-20261006-r1'
CONFIG = '00_SYSTEM/GENOS_NFS_PROBE.json'
DEFAULT_ROOT = Path(__file__).resolve().parents[2]
BASE = Path('/nfs-root/diamo')
MOUNT_ROOT = BASE


def configure_mount_root(base):
    """Allow the selected mount entry alias; keep logical data paths intact."""
    global MOUNT_ROOT
    base = Path(base)
    if not base.is_absolute() or '..' in base.parts:
        raise ValueError('absolute NFS mount root required: ' + str(base))
    actual = base.resolve(strict=True)
    if not actual.is_dir():
        raise ValueError('NFS mount root is not a directory: ' + str(base))
    MOUNT_ROOT = base
    return {'logical_root': str(base), 'actual_root': str(actual),
            'aliases': [{'path': str(part), 'actual_path': str(part.resolve(strict=True))}
                        for part in (base, *base.parents) if part.is_symlink()],
            'mount': mount_info(actual)}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def plain(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute plain path required')
    for part in (path, *path.parents):
        if part.is_symlink():
            if path.is_relative_to(MOUNT_ROOT) and (part == MOUNT_ROOT or MOUNT_ROOT.is_relative_to(part)):
                if not part.is_dir():
                    raise ValueError('broken/non-directory NFS mount alias: ' + str(part) + ' (requested: ' + str(path) + ')')
                continue
            raise ValueError('symlink path refused: ' + str(part) + ' (requested: ' + str(path) + ')')
    return path


def inside(base, relative):
    path = plain(base / relative)
    if not path.is_relative_to(base):
        raise ValueError('path outside selected root')
    return path


def metadata(path):
    plain(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('metadata exceeds 4 MiB')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('metadata must be an object')
    return value


def file_sample(path):
    """Bind fast probes to source bytes without hashing multi-GB payloads."""
    plain(path)
    before = path.stat()
    if not path.is_file():
        raise ValueError('regular file required')
    with path.open('rb') as stream:
        head = stream.read(1024 * 1024)
        stream.seek(max(0, before.st_size - 65536))
        tail = stream.read(65536)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('file changed during read')
    return {'bytes': after.st_size, 'head_sha256': hashlib.sha256(head).hexdigest(),
            'tail_sha256': hashlib.sha256(tail).hexdigest()}


def sqlite_read(path, preferred=(), *, require_row=False):
    plain(path)
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('active or unresolved SQLite sidecar; stop writers first')
    with path.open('rb') as stream:
        if stream.read(16) != b'SQLite format 3\x00':
            raise ValueError('not a SQLite database')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=.2)) as db:
        db.execute('PRAGMA query_only=ON')
        deadline = time.monotonic() + 5
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        table = next((name for name in preferred if name in tables), None)
        if preferred and table is None:
            raise ValueError('required SQL table absent')
        table = table or next(iter(tables), None)
        if table is None:
            raise ValueError('no SQL tables')
        quote = lambda text: '"' + text.replace('"', '""') + '"'
        columns = [r[1] for r in db.execute('PRAGMA table_info(' + quote(table) + ')')]
        column = next((c for c in ('text', 'json', 'payload', 'binding_json') if c in columns), columns[0])
        row = db.execute('SELECT substr(CAST(' + quote(column) + ' AS TEXT),1,4096) FROM ' + quote(table) + ' LIMIT 1').fetchone()
        if require_row and row is None:
            raise ValueError('required SQL data absent')
        sample = str(row[0] or '').encode() if row is not None else b''
        return {'table': table, 'row_present': row is not None,
                'sample_bytes': len(sample), 'sample_sha256': hashlib.sha256(sample).hexdigest(),
                'schema_version': db.execute('PRAGMA schema_version').fetchone()[0],
                'journal_mode': db.execute('PRAGMA journal_mode').fetchone()[0],
                'open_mode': 'ro&immutable=1; sidecars refused'}


def asset_paths(generation):
    m = metadata(generation / 'manifest.json')
    if m.get('schema_version') not in ('term-source-generation-v1', 'term-source-generation-v2'):
        raise ValueError('unsupported generation schema')
    paths = [('source_store', generation / 'store.sqlite', ('source_block', 'source_unit', 'document'), True)]
    metadata_files = [('generation_manifest', generation / 'manifest.json', None)]
    nav = m.get('navigation')
    if not isinstance(nav, dict):
        raise ValueError('navigation binding missing')
    nroot = inside(generation, nav['path'])
    metadata_files.append(('navigation_manifest', nroot / 'manifest.json', nav['manifest_sha256']))
    paths.append(('navigation_sql', nroot / 'navigation.sqlite', ('source',), True))
    fulltext = m.get('fulltext')
    if not isinstance(fulltext, dict):
        raise ValueError('fulltext binding missing')
    froot = inside(generation, fulltext['path'])
    fm = metadata(froot / 'manifest.json')
    metadata_files.append(('fulltext_manifest', froot / 'manifest.json', fulltext['manifest_sha256']))
    if fm.get('schema_version') == 'semantic-unit-fulltext-v1':
        paths.append(('fulltext_sql', froot / 'units.sqlite', ('unit',), True))
    elif fm.get('schema_version') == 'semantic-fulltext-v2':
        paths.append(('fulltext_sql', froot / 'fulltext.sqlite', ('source_fts',), True))
    else:
        raise ValueError('unsupported fulltext schema')
    glossary = m.get('glossary')
    if not isinstance(glossary, dict):
        raise ValueError('glossary binding missing')
    bundle = inside(generation, glossary['bundle'])
    gm = metadata(bundle / 'manifest.json')
    metadata_files.append(('glossary_manifest', bundle / 'manifest.json', glossary['manifest_sha256']))
    paths.append(('glossary_dictionary', inside(generation, glossary['dictionary']), (), True))
    for name in ('nodes.sqlite', 'graph.sqlite', 'identity.sqlite', 'translations.sqlite', 'lookup.sqlite'):
        path = bundle / name
        if path.is_file():
            paths.append(('glossary_' + path.stem, path, (), False))
    if gm.get('schema_version') == 'glossary-serving-v2' and not (bundle / 'nodes.sqlite').is_file():
        raise ValueError('compact glossary nodes missing')
    cache = inside(generation, glossary['cache'])
    receipt = inside(cache, glossary['cache_receipt'])
    metadata_files.append(('glossary_cache_receipt', receipt, glossary['cache_receipt_sha256']))
    paths.append(('glossary_cache_sql', receipt.with_suffix('.sqlite'), (), False))
    return m, metadata_files, paths


def memory_path(runtime, state=None):
    base = (state or runtime) / 'case-memory'
    pointer = base / 'SHORTCUT_CURRENT.json'
    if not pointer.exists():
        return base / 'cases-v4.sqlite', None
    value = metadata(pointer)
    if value.get('schema_version') != 'shortcut-store-pointer-v1':
        raise ValueError('shortcut pointer schema mismatch')
    digest = hashlib.sha256(json.dumps(value['receipt'], ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if digest != value['receipt_hash']:
        raise ValueError('shortcut receipt mismatch')
    selected = inside(base, value['path'])
    if selected.name != 'cases-v4.sqlite':
        raise ValueError('shortcut database name mismatch')
    return selected, pointer


def mount_info(path):
    try:
        path = Path(path).resolve()
        found = []
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            first, _, second = line.partition(' - ')
            fields = first.split()
            mount = Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4]))
            if path.is_relative_to(mount):
                found.append((len(mount.parts), {'mount_point': str(mount), 'fs_type': second.split()[0],
                                                 'read_only': 'ro' in fields[5].split(',')}))
        return max(found, key=lambda r: r[0])[1] if found else {'status': 'UNVERIFIED'}
    except (OSError, IndexError, ValueError):
        return {'status': 'UNVERIFIED'}


def probe(*, code_root=None, stage='code-serving', settings=None, nfs_base=BASE):
    started = time.monotonic()
    root = plain(Path(code_root or DEFAULT_ROOT).resolve(strict=True))
    settings = os.environ if settings is None else settings
    result = {'response_schema': REVISION, 'probe_revision': REVISION, 'request_id': uuid.uuid4().hex,
              'stage': stage, 'ok': False, 'checks': [], 'code_root': str(root),
              'python': {'executable': sys.executable, 'version': platform.python_version()},
              'process': {'pid': os.getpid(), 'uid': os.getuid(), 'gid': os.getgid()},
              'scope': 'NFS file reads, bounded SQL reads, metadata/sample and committed-code identity',
              'full_generation_integrity_verified': False, 'rag_model_execution_verified': False,
              'runtime_write_verified': False}
    def check(name, path, fn):
        row = {'name': name, 'path': str(path)}
        try:
            row.update(status='PASS', **(fn() or {}))
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            row.update(status='FAIL', error_type=type(exc).__name__, errno=getattr(exc, 'errno', None))
            if isinstance(exc, ValueError):
                row['reason'] = str(exc)
        result['checks'].append(row)
        return row
    try:
        c = metadata(root / CONFIG)
        if c.get('schema_version') != REVISION:
            raise ValueError('probe config schema mismatch')
        result['nfs_mount_entry'] = configure_mount_root(nfs_base)
        nfs_base = plain(nfs_base)
        generation, runtime = plain(Path(c['generation'])), plain(Path(c['runtime']))
        state = plain(Path(c['state'])) if c.get('state') else None
        receipt = plain(Path(c['receipt_path']))
        for path in (generation, runtime, receipt, *([state] if state else [])):
            if not path.is_relative_to(nfs_base) or path == nfs_base:
                raise ValueError('configured data outside NFS base')
        result.update(probe_id=c['probe_id'], generation=str(generation), runtime=str(runtime),
                      state=str(state) if state else None, mount=mount_info(generation))
        binding = metadata(receipt)
        if binding['probe_id'] != c['probe_id'] or binding['schema_version'] != REVISION:
            raise ValueError('receipt identity mismatch')
        if set(binding['code_files']) != set(c['code_paths']) or not re.fullmatch(r'[0-9a-f]{40,64}', binding['commit']):
            raise ValueError('committed file inventory or commit missing')
        result['expected_commit'] = binding['commit']
        for name, expected in binding['code_files'].items():
            path = inside(root, name)
            def code_match(path=path, expected=expected):
                actual = sha(path)
                if actual != expected:
                    raise ValueError('served code differs from committed checkout')
                return {'sha256': actual}
            check('committed_code:' + name, path, code_match)
            shared = inside(receipt.parent / 'code', name)
            def shared_match(shared=shared, expected=expected):
                actual = sha(shared)
                if actual != expected:
                    raise ValueError('NFS code hash mismatch')
                return {'sha256': actual}
            check('nfs_code:' + name, shared, shared_match)
        def environment():
            if stage == 'code-space':
                return {'selection': 'prepared-code-config', 'runtime_paths_match': True,
                        'generation_configured': True, 'runtime_configured': True,
                        'serving_environment_verified': False}
            configured = settings.get('GENOS_GENERATION', '').strip()
            if not configured and settings.get('GENOS_DATA_ROOT', '').strip():
                configured = metadata(plain(Path(settings['GENOS_DATA_ROOT'])) / 'generations/CURRENT.json')['path']
            actual_runtime = settings.get('GENOS_RUNTIME_DIR', '').strip()
            actual_state = settings.get('GENOS_STATE_DIR', '').strip() or None
            if stage == 'code-serving' and (configured != str(generation) or actual_runtime != str(runtime) or actual_state != (str(state) if state else None)):
                raise ValueError('serving path environment differs from prepared NFS data')
            return {'generation_configured': bool(configured), 'runtime_configured': bool(actual_runtime),
                    'runtime_paths_match': configured == str(generation) and actual_runtime == str(runtime) and actual_state == (str(state) if state else None)}
        check('serving_path_environment', root / CONFIG, environment)
        m, manifests, databases = asset_paths(generation)
        result['generation_id'] = m.get('generation_id')
        for name, path, expected in manifests:
            def meta_match(path=path, expected=expected):
                metadata(path)
                actual = sha(path)
                pinned = expected or c['generation_manifest_sha256']
                if actual != pinned:
                    raise ValueError('data metadata hash mismatch')
                return {'sha256': actual}
            check(name, path, meta_match)
        for name, path, tables, require_row in databases:
            def read(path=path, tables=tables, require_row=require_row):
                sample = file_sample(path)
                if sample != binding['immutable_samples'].get(str(path)):
                    raise ValueError('codespace/serving sample differs')
                return {'file_sample': sample, 'sql': sqlite_read(path, tables, require_row=require_row)}
            check(name, path, read)
        def runtime_directory():
            with os.scandir(plain(runtime)) as entries:
                return {'directory_readable': True, 'has_entries': next(entries, None) is not None}
        check('runtime_directory', runtime, runtime_directory)
        db, pointer = memory_path(runtime, state)
        if pointer:
            check('shortcut_pointer', pointer, lambda: {'sha256': sha(pointer)})
        if c.get('memory_database_required') or db.exists():
            check('shortcut_legal_wiki_sql', db, lambda: {'sql': sqlite_read(db, ('sw_knowledge', 'knowledge'), require_row=False)})
        else:
            result['checks'].append({'name': 'shortcut_legal_wiki_sql', 'path': str(db), 'status': 'NOT_CREATED',
                                     'required': False})
        legacy = runtime / 'case-memory/cases-v3.sqlite'
        if legacy.exists():
            check('legacy_cases_v3_sql', legacy, lambda: {'sql': sqlite_read(legacy, ('knowledge', 'goal'))})
        # Commit provenance may also be available in containers retaining .git.
        try:
            git = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=3)
            result['observed_git_commit'] = git.stdout.strip() if git.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            result['observed_git_commit'] = None
        if result['observed_git_commit'] and result['observed_git_commit'] != binding['commit']:
            check('checkout_commit', root, lambda: (_ for _ in ()).throw(ValueError('HEAD differs from prepared commit')))
        result['ok'] = all(row['status'] != 'FAIL' for row in result['checks'])
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        result['checks'].append({'name': 'probe_binding_or_assets', 'status': 'FAIL',
                                 'error_type': type(exc).__name__, 'errno': getattr(exc, 'errno', None),
                                 'path': str(getattr(exc, 'filename', None) or root / CONFIG),
                                 'reason': str(exc) if isinstance(exc, ValueError) else None})
    result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
    return result


async def gateway(data, *, code_root=None):
    import asyncio
    report = await asyncio.to_thread(probe, code_root=code_root, stage='code-serving')
    return {'status': 200 if report['ok'] else 503, 'body': report}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--code-root', type=Path, default=DEFAULT_ROOT)
    ap.add_argument('--output', type=Path)
    a = ap.parse_args(argv)
    result = probe(code_root=a.code_root, stage='code-space')
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if a.output:
        a.output.write_text(text + '\n', encoding='utf-8')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
