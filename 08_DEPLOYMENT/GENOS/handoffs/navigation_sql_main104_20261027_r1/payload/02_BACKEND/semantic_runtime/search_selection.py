"""Generation-bound search visibility; immutable SQLite bytes are never changed.

An explicit operator plan lives beside a generation or in deployed code.
Connection-local TEMP views also protect direct reads and navigation consumers.
No model, structure, embedding or index build occurs here.
"""
import hashlib
import json
from pathlib import Path
from .contracts import digest, sha

VERSION = 'filename-search-selection-v1'
LATEST_VERSION = 'filename-search-selection-v2'
CODE_ROOT = Path(__file__).resolve().parents[2]
CODE_SELECTION_PATH = '00_SYSTEM/SEARCH_SELECTION/generation.json'


def selection_path(generation):
    generation = Path(generation).resolve()
    return generation.parent / 'SEARCH_SELECTION' / (generation.name + '.json')


def file_state(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('search selection cannot use symlinks')
    if not path.exists():
        return None
    s = path.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def runtime_binding(generation, *, verify=True):
    """Explicit code-bundled metadata for the operator-selected generation.

    Other data generations keep their existing NFS sidecar. A configured code
    selection never falls back to NFS when the bundled file is missing/invalid.
    """
    generation = Path(generation).resolve()
    config = CODE_ROOT / '00_SYSTEM/GENOS_SERVING_PATHS.json'
    state = file_state(config)
    if state is None:
        return selection_path(generation), None, None
    value = json.loads(config.read_text('utf-8'))
    if not isinstance(value, dict):
        raise ValueError('invalid code search selection deployment config')
    override = value.get('search_selection')
    if override is None:
        return selection_path(generation), None, None
    if (value.get('schema_version') != 'genos-serving-paths-v1' or
            value.get('selection') != 'operator-fixed'):
        raise ValueError('invalid code search selection deployment binding')
    selected = value.get('generation')
    if not isinstance(selected, str) or not Path(selected).is_absolute():
        raise ValueError('absolute generation required for code search selection')
    if generation != Path(selected).resolve():
        return selection_path(generation), None, None
    if (not isinstance(override, dict) or set(override) != {'path', 'sha256'} or
            override.get('path') != CODE_SELECTION_PATH or
            not isinstance(override.get('sha256'), str) or
            len(override['sha256']) != 64 or
            any(c not in '0123456789abcdef' for c in override['sha256'])):
        raise ValueError('invalid code search selection path/hash')
    path = CODE_ROOT / CODE_SELECTION_PATH
    if file_state(path) is None:
        raise ValueError('configured code search selection is missing: ' + str(path))
    if verify and sha(path) != override['sha256']:
        raise ValueError('code search selection hash mismatch')
    if verify and sha(generation/'manifest.json') != value.get('generation_manifest_sha256'):
        raise ValueError('code search selection generation manifest mismatch')
    if file_state(config) != state:
        raise ValueError('code search selection configuration changed while reading')
    return path, override['sha256'], state


class Selection:
    def __init__(self, generation, manifest):
        self.generation = Path(generation).resolve()
        self._runtime_binding = runtime_binding(self.generation)
        self.path = self._runtime_binding[0]
        self.state = file_state(self.path)
        self.excluded = frozenset()
        self.fingerprint = None
        self.value = None
        self.latest = {}
        self.native_latest_verified = False
        if self.state is not None:
            raw = self.path.read_bytes()
            if (self._runtime_binding[1] is not None and
                    hashlib.sha256(raw).hexdigest() != self._runtime_binding[1]):
                raise ValueError('code search selection hash changed while reading')
            value = json.loads(raw)
            if (value.get('schema_version') not in {VERSION, LATEST_VERSION} or
                    value.get('generation_id') != manifest['generation_id'] or
                    value.get('store_sha256') != manifest['store_sha256'] or
                    value.get('manifest_sha256') != sha(Path(generation) / 'manifest.json')):
                raise ValueError('stale or invalid search selection binding')
            rows = value.get('excluded')
            if not isinstance(rows, list) or any(not isinstance(r, dict) or
                    not isinstance(r.get('document_id'), str) or not r['document_id'] or
                    not isinstance(r.get('source_artifact_sha256'), str) for r in rows):
                raise ValueError('invalid search exclusion records')
            self.excluded = frozenset(r['document_id'] for r in rows)
            if len(self.excluded) != len(rows):
                raise ValueError('duplicate search exclusion IDs')
            if value['schema_version'] == LATEST_VERSION:
                marks = value.get('latest_documents')
                if not isinstance(marks, list) or any(not isinstance(r, dict) or not isinstance(r.get('document_id'), str) or type(r.get('is_latest')) is not bool for r in marks):
                    raise ValueError('invalid latest document marks')
                self.latest = {r['document_id']: r for r in marks}
                if len(self.latest) != len(marks) or {k for k, r in self.latest.items() if not r['is_latest']} != set(self.excluded):
                    raise ValueError('latest mark/exclusion mismatch')
            self.fingerprint = digest(value)
            self.value = value
        self.check_unchanged()

    def require_latest(self):
        self.check_unchanged()
        if not self.native_latest_verified and (self.value is None or self.value.get('schema_version') != LATEST_VERSION):
            raise ValueError('latest document selection required; run pipeline search-selection --latest before serving')

    def check_unchanged(self):
        if (file_state(self.path) != self.state or
                runtime_binding(self.generation, verify=False) != self._runtime_binding):
            raise ValueError('search selection changed; restart serving before reuse')

    def verify_documents(self, db):
        if self.value is None:
            from .filename_versions import inventory_generation
            rows, _ = inventory_generation(self.generation)
            self.native_latest_verified = True
            for did in {r['document_id'] for r in rows}:
                value = json.loads(db.execute('SELECT json FROM document WHERE document_id=?', (did,)).fetchone()[0])
                meta = value.get('document_metadata') or {}; version = meta.get('filename_version') or {}
                if not (meta.get('is_latest') is True and version.get('is_latest') is True and version.get('policy') == 'user-approved-retained-set-latest-v2' and len(version.get('exceptions_sha256', '')) == 64):
                    self.native_latest_verified = False; break
            return
        if self.value['schema_version'] == LATEST_VERSION:
            from .filename_versions import inventory_generation, select, latest_marks
            rows, binding = inventory_generation(self.generation)
            if binding['metadata_sha256'] != self.value.get('metadata_sha256'):
                raise ValueError('latest metadata changed')
            decisions = select(rows, self.value['exceptions']['value'])
            if latest_marks(decisions) != self.value['latest_documents']:
                raise ValueError('latest marks do not match approved selection')
        for row in self.value['excluded']:
            found = db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',
                               (row['document_id'],)).fetchone()
            if found is None or found[0] != row['source_artifact_sha256']:
                raise ValueError('search exclusion document/hash mismatch')
        if db.execute('SELECT count(*) FROM document').fetchone()[0] <= len(self.excluded):
            raise ValueError('search selection cannot exclude every document')

    def bind(self, db, *, navigation=False):
        """Install only TEMP objects on this private connection, then restore RO.

        All main objects (including compact logical views) are read unchanged.
        A reference touching an excluded endpoint is withheld, never retargeted.
        """
        self.check_unchanged()
        if not self.excluded and not self.latest:
            return
        from .resident_data import _readonly
        db.set_authorizer(None)
        try:
            db.execute('PRAGMA query_only=OFF')
            db.execute('CREATE TEMP TABLE search_excluded(document_id TEXT PRIMARY KEY) WITHOUT ROWID')
            db.executemany('INSERT INTO search_excluded VALUES (?)', [(d,) for d in sorted(self.excluded)])
            db.execute('CREATE TEMP TABLE latest_document(document_id TEXT PRIMARY KEY, mark TEXT) WITHOUT ROWID')
            db.executemany('INSERT INTO latest_document VALUES (?,?)', [(k, json.dumps(v, ensure_ascii=False)) for k, v in self.latest.items() if v['is_latest']])
            objects = {r[0] for r in db.execute("SELECT name FROM main.sqlite_master WHERE type IN ('table','view')")}
            def view(name, predicate):
                if name in objects:
                    db.execute('CREATE TEMP VIEW "'+name+'" AS SELECT * FROM main."'+name+'" AS original WHERE '+predicate)
            visible = 'original.document_id NOT IN (SELECT document_id FROM temp.search_excluded)'
            if not navigation:
                if self.latest:
                    columns = [r[1] for r in db.execute('PRAGMA main.table_info(document)')]
                    projection = ','.join(("json_set(original.json, '$.document_metadata.is_latest', json('true'), '$.document_metadata.latest_selection', json(m.mark)) AS json" if n == 'json' else 'original."'+n+'"') for n in columns)
                    # Unclassified/external documents do not acquire an internal latest mark.
                    projection = projection.replace('json_set(original.json,', 'CASE WHEN m.document_id IS NULL THEN original.json ELSE json_set(original.json,').replace('json(m.mark)) AS json', 'json(m.mark)) END AS json')
                    db.execute('CREATE TEMP VIEW document AS SELECT '+projection+' FROM main.document original LEFT JOIN temp.latest_document m ON m.document_id=original.document_id WHERE '+visible)
                else: view('document', visible)
                for name in ('source_unit', 'source_block', 'block_payload'):
                    view(name, visible)
            else:
                for name in ('source', 'source_literal', 'definition', 'document_frame'):
                    view(name, visible)
                for name in ('occurrence', 'source_unit_map', 'structure_anchor'):
                    view(name, 'original.source_id IN (SELECT id FROM temp.source)')
                # reference_end includes resolved targets and the origin; candidates
                # are checked separately, since they are not necessarily endpoints.
                hidden = []
                for name in ('reference_end', 'reference_target', 'reference_candidate'):
                    if name in objects:
                        hidden.append('original.id NOT IN (SELECT e.reference_id FROM main.'+name+' e '
                                      'WHERE e.source_id IN (SELECT s.id FROM main.source s '
                                      'WHERE s.document_id IN (SELECT document_id FROM temp.search_excluded)))')
                view('reference', visible + (' AND ' + ' AND '.join(hidden) if hidden else ''))
                for name in ('reference_end', 'reference_target', 'reference_candidate', 'reference_candidate_end'):
                    view(name, 'original.reference_id IN (SELECT id FROM temp.reference)')
                if 'definition_reference' in objects:
                    view('definition_reference', 'EXISTS (SELECT 1 FROM temp.definition d WHERE d.id=original.definition_id) AND EXISTS (SELECT 1 FROM temp.reference r WHERE r.id=original.reference_id)')
            db.commit()  # TEMP only; main is a read-only URI / immutable resident copy.
        finally:
            db.execute('PRAGMA query_only=ON')
            db.set_authorizer(_readonly)
        self.check_unchanged()
