"""Immutable original-text generations for term navigation; no meaning extraction."""
import json
import sqlite3
from pathlib import Path
from .contracts import sha, write

VERSION = 'term-source-generation-v1'
TABLES = ('document', 'source_unit', 'source_block')


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
        if self.manifest['schema_version']!=VERSION:raise ValueError('source generation migration required')
        if verify and sha(self.path/'store.sqlite')!=self.manifest['store_sha256']:
            raise ValueError('generation artifact hash mismatch')
        self.db=sqlite3.connect((self.path/'store.sqlite').as_uri()+'?mode=ro',uri=True,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA query_only=ON')
        tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables!=set(TABLES):
            self.db.close()
            raise ValueError('source generation contains unexpected tables')

    def close(self):self.db.close()

    def source(self,did,bid):
        r=self.db.execute('SELECT * FROM source_block WHERE document_id=? AND block_id=?',(did,str(bid))).fetchone()
        if not r:raise KeyError((did,bid))
        return dict(r)

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
