"""Generation-bound search visibility; immutable SQLite bytes are never changed.

An explicit operator plan lives beside, not inside, a completed generation.
Connection-local TEMP views also protect direct reads and navigation consumers.
No model, structure, embedding or index build occurs here.
"""
import json
from pathlib import Path
from .contracts import digest, sha

VERSION = 'filename-search-selection-v1'


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


class Selection:
    def __init__(self, generation, manifest):
        self.path = selection_path(generation)
        self.state = file_state(self.path)
        self.excluded = frozenset()
        self.fingerprint = None
        self.value = None
        if self.state is not None:
            value = json.loads(self.path.read_text('utf-8'))
            if (value.get('schema_version') != VERSION or
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
            self.fingerprint = digest(value)
            self.value = value
        self.check_unchanged()

    def check_unchanged(self):
        if file_state(self.path) != self.state:
            raise ValueError('search selection changed; restart serving before reuse')

    def verify_documents(self, db):
        if self.value is None:
            return
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
        if not self.excluded:
            return
        from .resident_data import _readonly
        db.set_authorizer(None)
        try:
            db.execute('PRAGMA query_only=OFF')
            db.execute('CREATE TEMP TABLE search_excluded(document_id TEXT PRIMARY KEY) WITHOUT ROWID')
            db.executemany('INSERT INTO search_excluded VALUES (?)', [(d,) for d in sorted(self.excluded)])
            objects = {r[0] for r in db.execute("SELECT name FROM main.sqlite_master WHERE type IN ('table','view')")}
            def view(name, predicate):
                if name in objects:
                    db.execute('CREATE TEMP VIEW "'+name+'" AS SELECT * FROM main."'+name+'" AS original WHERE '+predicate)
            visible = 'original.document_id NOT IN (SELECT document_id FROM temp.search_excluded)'
            if not navigation:
                for name in ('document', 'source_unit', 'source_block', 'block_payload'):
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
            db.commit()  # TEMP only; main is a read-only URI / immutable resident copy.
        finally:
            db.execute('PRAGMA query_only=ON')
            db.set_authorizer(_readonly)
        self.check_unchanged()
