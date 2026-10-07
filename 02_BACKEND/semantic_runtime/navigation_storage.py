"""Separate build evidence from serving navigation without changing retrieval.

The audit SQLite is an exact immutable copy of the completed pre-split index.
It retains the construction context as well as every accepted/held evidence row.
Serving never needs to open this artifact. Existing monolithic indexes stay valid.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile

from .contracts import sha, write

VERSION = 'term-navigation-storage-v1'
AUDIT_TABLES = ('link_catalogue', 'link_occurrence', 'occurrence_evidence', 'occurrence_origin')


def _ro(path):
    path = Path(path).resolve()
    wal = Path(str(path) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Navigation audit requires a completed database without WAL')
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def _tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def _projection_schema(db, runtime_tables):
    objects = list(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
    # Unknown SQL machinery keeps the established copy/drop/VACUUM path.
    if any(kind not in ('table','index') for kind,_,_,_ in objects):
        return None
    selected = [r for r in objects if r[2] in runtime_tables and r[3]]
    if any('VIRTUAL TABLE' in sql.upper() or 'AUTOINCREMENT' in sql.upper()
           for _,_,_,sql in selected):
        return None
    for table in runtime_tables:
        if any(r[6] != 0 for r in db.execute('PRAGMA table_xinfo('+_quote(table)+')')):
            return None
    return selected


def _quote(identifier):
    return '"'+identifier.replace('"','""')+'"'


def _project_runtime(audit, index, schema, *, compact=False):
    """Copy only live runtime rows, retaining SQL definitions and row identities."""
    with closing(sqlite3.connect(index)) as db:
        db.execute('ATTACH DATABASE ? AS construction', (audit.as_uri()+'?mode=ro',))
        if compact: schema = [r for r in schema if r[2] != 'occurrence']
        for kind, name, _, sql in schema:
            if kind != 'table':
                continue
            db.execute(sql)
            columns = [_quote(r[1]) for r in db.execute('PRAGMA construction.table_info('+_quote(name)+')')]
            if 'WITHOUT ROWID' not in sql.upper():
                # Preserve implicit row IDs too; audit/serving consumers may use them.
                declared = {r[1].lower() for r in db.execute('PRAGMA construction.table_info('+_quote(name)+')')}
                rowid = next((alias for alias in ('rowid','_rowid_','oid') if alias not in declared), None)
                if rowid is None:
                    raise ValueError('Runtime table shadows every rowid alias')
                columns.insert(0,rowid)
            fields = ','.join(columns)
            db.execute('INSERT INTO '+_quote(name)+' ('+fields+') SELECT '+fields+' FROM construction.'+_quote(name))
        for kind, _, _, sql in schema:
            if kind == 'index':
                db.execute(sql)
        if compact:
            from .compact_storage import occurrence_projection
            occurrence_projection(db)
        db.commit()


def separate_navigation(index, audit_directory, *, compact=False):
    """Mutate only a NEW unpublished index; preserve its exact pre-split bytes."""
    index, directory = Path(index).resolve(), Path(audit_directory).resolve()
    if directory.exists():
        raise ValueError('Navigation audit output already exists; use a new output')
    if directory == index.parent or directory.is_relative_to(index.parent):
        raise ValueError('Build audit must be outside the serving navigation directory')
    with closing(_ro(index)) as db:
        tables = _tables(db)
        selected = tables.intersection(AUDIT_TABLES)
        if not selected:
            return None
        if selected != set(AUDIT_TABLES):
            raise ValueError('Incomplete navigation construction evidence')
        projection = _projection_schema(db, tables - set(AUDIT_TABLES))
        counts = {name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
                  for name in AUDIT_TABLES}
    if index.stat().st_nlink != 1:
        raise ValueError('Refusing to mutate a shared/hardlinked navigation database')
    if compact and projection is None: raise ValueError('unsupported compact navigation SQL schema')
    runtime_tables = tables - set(AUDIT_TABLES)
    if compact: runtime_tables = (runtime_tables - {'occurrence'}) | {'occurrence_keys'}
    original_sha = sha(index)
    original_bytes = index.stat().st_size
    directory.mkdir(parents=True)
    audit = directory / 'navigation.sqlite'
    moved = projection is not None and index.stat().st_dev == directory.stat().st_dev
    try:
        if moved:
            os.rename(index, audit)
            _project_runtime(audit, index, projection, compact=compact)
        else:
            if compact: raise ValueError('compact navigation audit must share filesystem')
            shutil.copyfile(index, audit)
            with closing(sqlite3.connect(index)) as db:
                for name in AUDIT_TABLES:
                    db.execute(f'DROP TABLE "{name}"')
                db.commit()
                db.execute('VACUUM')
        if sha(audit) != original_sha:
            raise ValueError('Navigation construction audit copy changed')
        with closing(_ro(index)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Compact navigation integrity failure')
            if _tables(db) != runtime_tables:
                raise ValueError('Compact navigation table coverage mismatch')
    except BaseException:
        # Even interruption restores the original unpublished index byte-for-byte.
        if moved and audit.exists():
            index.unlink(missing_ok=True)
            os.rename(audit, index)
            directory.rmdir()
        raise
    compact_sha = sha(index)
    manifest = {
        'schema_version': 'term-navigation-storage-v2' if compact else VERSION, 'audit_policy': 'exact-completed-index-snapshot',
        'audit_file': 'navigation.sqlite', 'audit_sha256': original_sha,
        'audit_bytes': original_bytes, 'serving_index_sha256': compact_sha,
        'serving_index_bytes': index.stat().st_size,
        'construction_tables': counts, 'runtime_tables': sorted(runtime_tables), 'runtime_views': ['occurrence'] if compact else [],
        'compiler_sha256': sha(__file__), 'llm_calls': 0,
        'separation_strategy': 'runtime-projection' if moved else 'copy-drop-vacuum',
    }
    write(directory / 'manifest.json', manifest)
    return {'schema_version': manifest['schema_version'], 'mode': 'separate-build-audit',
            'audit_manifest_sha256': sha(directory / 'manifest.json'),
            'pre_split_index_sha256': original_sha,
            'construction_tables': list(AUDIT_TABLES)}


def verify_audit(directory, *, expected_manifest_sha256, expected_index_sha256):
    directory = Path(directory).resolve()
    manifest = directory / 'manifest.json'
    if sha(manifest) != expected_manifest_sha256:
        raise ValueError('Navigation audit manifest changed')
    value = json.loads(manifest.read_text())
    if (value.get('schema_version') not in {VERSION, 'term-navigation-storage-v2', 'term-navigation-storage-v3'}
            or value.get('audit_file') != 'navigation.sqlite'
            or value.get('serving_index_sha256') != expected_index_sha256):
        raise ValueError('Navigation audit/index binding mismatch')
    audit = directory / 'navigation.sqlite'
    if audit.stat().st_size != value['audit_bytes'] or sha(audit) != value['audit_sha256']:
        raise ValueError('Navigation audit snapshot changed')
    with closing(_ro(audit)) as db:
        if not set(AUDIT_TABLES) <= _tables(db):
            raise ValueError('Navigation audit evidence missing')
    return value


def verify_build(output):
    """Offline/resume verification includes audit; request serving excludes it."""
    output = Path(output).resolve()
    result = json.loads((output / 'result.json').read_text())
    generation = output / 'generation'
    if sha(generation / 'manifest.json') != result['manifest_sha256']:
        raise ValueError('Compact generation manifest changed')
    value = json.loads((generation / 'manifest.json').read_text())
    nav = generation / value['navigation']['path']
    nav.resolve().relative_to(generation)
    if sha(nav / 'manifest.json') != value['navigation']['manifest_sha256']:
        raise ValueError('Compact navigation manifest changed')
    index = json.loads((nav / 'manifest.json').read_text())
    if sha(nav / 'navigation.sqlite') != index['index_sha256']:
        raise ValueError('Compact navigation database changed')
    binding = result.get('navigation_audit')
    if not binding or binding.get('path') != 'audit/navigation':
        raise ValueError('Missing compact navigation audit receipt')
    storage = index.get('storage', {})
    if (storage.get('schema_version') not in {VERSION, 'term-navigation-storage-v2', 'term-navigation-storage-v3'}
            or storage.get('audit_manifest_sha256') != binding['manifest_sha256']):
        raise ValueError('Compact navigation/audit manifest binding mismatch')
    audit = verify_audit(output / binding['path'],
                         expected_manifest_sha256=binding['manifest_sha256'],
                         expected_index_sha256=index['index_sha256'])
    with closing(_ro(nav / 'navigation.sqlite')) as db:
        if _tables(db).intersection(AUDIT_TABLES) or _tables(db) != set(audit['runtime_tables']):
            raise ValueError('Compact serving table coverage changed')
    from lawrag.pipeline.term_serving_bundle import verify_assets
    if 'glossary' in value:
        verify_assets(generation)
    else:
        from .storage import Store
        from .term_index import TermIndex
        with closing(Store(generation)) as store:
            TermIndex(nav, store)
    return result


def compact_generation(source, output):
    """Derive an explicitly selected generation, preserving all runtime payloads."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Compact output must be separate from the parent generation')
    parent = json.loads((source / 'manifest.json').read_text())
    identity = {'source_manifest_sha256': sha(source / 'manifest.json'),
                'source_generation': str(source), 'compiler_sha256': sha(__file__)}
    if output.exists():
        result = verify_build(output)
        if result['identity'] != identity:
            raise ValueError('Compact generation input changed; use a new output')
        return result
    nav_path = Path(parent['navigation']['path'])
    (source / nav_path).resolve().relative_to(source)
    parent_nav = json.loads((source / nav_path / 'manifest.json').read_text())
    if sha(source / nav_path / 'manifest.json') != parent['navigation']['manifest_sha256']:
        raise ValueError('Parent navigation manifest changed')
    if sha(source / nav_path / 'navigation.sqlite') != parent_nav['index_sha256']:
        raise ValueError('Parent navigation database changed')
    if parent_nav.get('storage'):
        raise ValueError('Parent is already separated; select its original monolithic generation')
    from .storage import Store
    with closing(Store(source)):
        pass
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
    try:
        def copy_payload(src, dst):
            # Only navigation SQLite and JSON receipts will change in this derivation.
            if Path(src).suffix == '.json' or Path(src).name == 'navigation.sqlite':
                return shutil.copyfile(src, dst)
            try:
                os.link(src, dst)
                return dst
            except OSError:
                return shutil.copyfile(src, dst)
        generation = temporary / 'generation'
        shutil.copytree(source, generation, copy_function=copy_payload,
                        ignore=shutil.ignore_patterns('__pycache__'))
        nav = generation / nav_path
        storage = separate_navigation(nav / 'navigation.sqlite', temporary / 'audit/navigation')
        if storage is None:
            raise ValueError('Selected generation has no construction audit to separate')
        index = {**parent_nav, 'index_sha256': sha(nav / 'navigation.sqlite'), 'storage': storage}
        (nav / 'manifest.json').unlink()
        write(nav / 'manifest.json', index)
        value = {**parent, 'navigation': {'path': parent['navigation']['path'],
                                        'manifest_sha256': sha(nav / 'manifest.json')}}
        if parent.get('fulltext'):
            fulltext = generation / parent['fulltext']['path']
            fulltext.resolve().relative_to(generation)
            if sha(fulltext / 'manifest.json') != parent['fulltext']['manifest_sha256']:
                raise ValueError('Parent fulltext manifest changed')
            ft = json.loads((fulltext / 'manifest.json').read_text())
            ft['navigation_index_sha256'] = index['index_sha256']
            (fulltext / 'manifest.json').unlink()
            write(fulltext / 'manifest.json', ft)
            value['fulltext'] = {**parent['fulltext'],
                                'manifest_sha256': sha(fulltext / 'manifest.json'),
                                'navigation_index_sha256': index['index_sha256']}
        (generation / 'manifest.json').unlink()
        write(generation / 'manifest.json', value)
        result = {'schema_version': 'navigation-storage-derivation-v1', 'identity': identity,
                  'generation': 'generation', 'manifest_sha256': sha(generation / 'manifest.json'),
                  'navigation_audit': {'path': 'audit/navigation',
                                      'manifest_sha256': storage['audit_manifest_sha256']},
                  'llm_calls': 0, 'activated': False, 'quality_certified': False}
        write(temporary / 'result.json', result)
        verify_build(temporary)
        if sha(source / 'manifest.json') != identity['source_manifest_sha256']:
            raise ValueError('Parent generation changed during compaction')
        if output.exists():
            raise ValueError('Compact generation output appeared during execution')
        os.rename(temporary, output)
        return result
    except BaseException:
        shutil.rmtree(temporary)
        raise
