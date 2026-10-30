"""Immutable original-text generations for term navigation; no meaning extraction."""
import json
import sqlite3
import threading
from pathlib import Path
from .contracts import sha, write, digest

VERSION = 'term-source-generation-v1'
TABLES = ('document', 'source_unit', 'source_block')
_VERIFIED_STORE = {}
_VERIFY_LOCK = threading.Lock()


def verified_store_digest(path):
    """Return the already verified pin only while the same file state holds."""
    path=Path(path).resolve();stat=path.stat()
    current=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    with _VERIFY_LOCK:
        return next((pin for (file,pin),state in _VERIFIED_STORE.items()
                     if file==path and state==current), None)


def verify_store_binding(path, expected):
    """Reuse a process-local hash proof while an immutable store's stat is fixed."""
    path = Path(path).resolve()
    def signature():
        stat = path.stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    with _VERIFY_LOCK:
        before = signature()
        if _VERIFIED_STORE.get((path, expected)) == before:
            return
        actual = sha(path)
        after = signature()
        if before != after or actual != expected:
            raise ValueError('generation artifact hash mismatch')
        if len(_VERIFIED_STORE) >= 128:
            _VERIFIED_STORE.pop(next(iter(_VERIFIED_STORE)))
        _VERIFIED_STORE[(path, expected)] = after


def publish(root, source_store, output, *, data_status='DRAFT', export_allowed=False, scope=None):
    source_store, output = Path(source_store).resolve(), Path(output)
    if data_status not in {'DRAFT', 'APPROVED', 'EXAMPLE'}:
        raise ValueError('unknown data status')
    if output.exists():
        raise ValueError('immutable generation already exists')
    source_hash = sha(source_store)
    output.mkdir(parents=True)
    db = sqlite3.connect(output / 'store.sqlite')
    try:
        db.execute('ATTACH DATABASE ? AS source', (source_store.as_uri() + '?mode=ro',))
        for table in TABLES:
            db.execute(f'CREATE TABLE {table} AS SELECT * FROM source.{table}')
        db.executescript("""
            CREATE UNIQUE INDEX document_pk ON document(document_id);
            CREATE UNIQUE INDEX unit_pk ON source_unit(document_id,unit_id);
            CREATE UNIQUE INDEX block_pk ON source_block(document_id,block_id);
            CREATE INDEX block_range ON source_block(document_id,CAST(block_id AS INTEGER));
        """)
        if db.execute('SELECT 1 FROM source_block b LEFT JOIN document d USING(document_id) WHERE d.document_id IS NULL OR b.source_artifact_sha256 != d.source_artifact_sha256 LIMIT 1').fetchone():
            raise ValueError('source document/block provenance mismatch')
        if db.execute('SELECT 1 FROM source_block b LEFT JOIN source_unit u ON b.document_id=u.document_id AND b.unit_id=u.unit_id WHERE b.unit_id IS NOT NULL AND u.unit_id IS NULL LIMIT 1').fetchone():
            raise ValueError('source block unit missing')
        if db.execute('SELECT 1 FROM source_unit u LEFT JOIN source_unit p ON u.document_id=p.document_id AND u.parent_id=p.unit_id WHERE u.parent_id IS NOT NULL AND p.unit_id IS NULL LIMIT 1').fetchone():
            raise ValueError('source ancestor missing')
        known={r[0] for r in db.execute('SELECT document_id FROM document')}
        if not known:raise ValueError('source generation is empty')
        if scope is not None and set(scope['document_version_ids']) != known:
            raise ValueError('source generation scope mismatch')
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':raise ValueError('source integrity failed')
        counts={t:db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in TABLES}
    finally:
        db.close()
    if sha(source_store) != source_hash:raise ValueError('source changed during publication')
    manifest={'schema_version':VERSION, 'generation_id':output.name, 'data_status':data_status,
              'export_allowed':export_allowed, 'store_sha256':sha(output/'store.sqlite'),
              'source_store_sha256':source_hash, 'scope':scope or {'document_version_ids':sorted(known)},
              'counts':counts, 'quality_certified':False}
    write(output/'manifest.json',manifest)
    return manifest


class Store:
    def __init__(self,path,*,verify=True):
        self.path=Path(path).resolve()
        self.manifest=json.loads((self.path/'manifest.json').read_text())
        from .search_selection import Selection
        self.selection = Selection(self.path, self.manifest)
        self._binding_state = self.binding_signature()
        if self.manifest['schema_version'] not in {VERSION, 'term-source-generation-v2'}:raise ValueError('source generation migration required')
        if verify:
            verify_store_binding(self.path/'store.sqlite', self.manifest['store_sha256'])
        if verify:
            from .resident_data import POOL
            self.db=POOL.connect(self.path/'store.sqlite', expected=self.manifest['store_sha256'])
        else:
            self.db=sqlite3.connect((self.path/'store.sqlite').as_uri()+'?mode=ro',uri=True,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA query_only=ON')
        tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = set(TABLES) if self.manifest['schema_version']==VERSION else {'document','source_unit','block_payload'}
        if tables!=expected:
            self.db.close()
            raise ValueError('source generation contains unexpected tables')
        try:
            self.selection.verify_documents(self.db)
            self.selection.bind(self.db)
            self.check_unchanged()
        except BaseException:
            self.db.close()
            raise

    def close(self):self.db.close()

    def binding_signature(self):
        states = []
        for name in ('manifest.json', 'store.sqlite'):
            s = (self.path/name).stat()
            states.append((s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns))
        self.selection.check_unchanged()
        return (str(self.path), digest(self.manifest), *states, self.selection.fingerprint)

    def check_unchanged(self):
        if self.binding_signature() != self._binding_state:
            raise ValueError('source generation changed; reopen and verify before reuse')

    def source(self,did,bid):
        self.check_unchanged()
        r=self.db.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',(did,str(bid))).fetchone()
        if not r:raise KeyError((did,bid))
        return dict(r)

    def sources(self, did, bids):
        """Bounded batch read preserving caller order, duplicates and missing-ID errors."""
        self.check_unchanged()
        requested = [str(b) for b in bids]
        ids = list(dict.fromkeys(requested))
        found = {}
        for start in range(0, len(ids), 800):
            part = list(dict.fromkeys(ids[start:start+800]))
            marks = ','.join('?' for _ in part)
            found.update((str(r['block_id']), dict(r)) for r in self.db.execute(
                'SELECT * FROM source_block WHERE document_id=? AND block_id IN ('+marks+')', [did,*part]))
        self.check_unchanged()
        for b in requested:
            if b not in found:raise KeyError((did,b))
        return [dict(found[b]) for b in requested]

    def source_lengths(self, did, bids):
        """Exact codepoint lengths from the same bound source view, no body copy."""
        self.check_unchanged()
        requested = [str(b) for b in bids]
        ids = list(dict.fromkeys(requested)); found = {}
        for start in range(0, len(ids), 800):
            part = ids[start:start+800]
            marks = ','.join('?' for _ in part)
            for bid, size, nul_text in self.db.execute(
                'SELECT block_id,LENGTH(text),CASE WHEN instr(text,char(0))>0 THEN text END '
                'FROM source_block WHERE document_id=? AND block_id IN ('+marks+')', [did,*part]):
                found[str(bid)] = len(nul_text) if nul_text is not None else size
        self.check_unchanged()
        for b in requested:
            if b not in found:raise KeyError((did,b))
        return {b:found[b] for b in requested}

    def source_scope(self,did,bid):
        source=self.source(did,bid)
        uid=source['unit_id']
        if uid is not None and self.db.execute('SELECT 1 FROM source_unit WHERE document_id=? AND unit_id=?',(did,str(uid))).fetchone():
            return self.section(did,uid)
        # A raw block without a unit is valid source, not a made-up article.
        doc=self.db.execute('SELECT name FROM document WHERE document_id=?',(did,)).fetchone()
        return {'document_id':did,'document_name':doc[0],'unit_id':None,'title':'','ancestors':[],
                'blocks':[source],'unresolved_reason':'SOURCE_WITHOUT_STRUCTURAL_UNIT'}

    def section(self,did,uid):
        self.check_unchanged()
        r=self.db.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',(did,str(uid))).fetchone()
        if not r:raise KeyError((did,uid))
        unit=json.loads(r[0]);lo,hi=unit['span'];ancestors=[];current=str(uid);seen=set()
        while current is not None:
            if current in seen:raise ValueError('ancestor cycle')
            seen.add(current);row=self.db.execute('SELECT parent_id,json FROM source_unit WHERE document_id=? AND unit_id=?',(did,current)).fetchone()
            if not row:raise ValueError('missing ancestor')
            v=json.loads(row['json']);ancestors.append({'id':current,'title':v.get('title',v.get('surface','')),'family':v.get('family')})
            current=str(row['parent_id']) if row['parent_id'] is not None else None
        doc=self.db.execute('SELECT name FROM document WHERE document_id=?',(did,)).fetchone()
        return {'document_id':did,'document_name':doc[0],'unit_id':str(uid),'title':unit.get('title',''),
                'ancestors':list(reversed(ancestors)),'blocks':[dict(x) for x in self.db.execute(
                    'SELECT block_id,unit_id,text FROM source_block WHERE document_id=? AND CAST(block_id AS INTEGER)>=? '
                    'AND CAST(block_id AS INTEGER)<? ORDER BY CAST(block_id AS INTEGER)',(did,lo,hi))]}
