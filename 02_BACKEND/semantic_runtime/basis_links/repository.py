"""Append-only revisions/bindings with atomic CAS, event and idempotency receipt."""
from contextlib import contextmanager
import json
import sqlite3
from .contracts import BasisError,require,encoded,digest,now
from ..state_sqlite import connect

DDL='''
CREATE TABLE IF NOT EXISTS basis_head(link_id TEXT PRIMARY KEY,team_id TEXT NOT NULL,revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS basis_revision(link_id TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(link_id,revision));
CREATE TABLE IF NOT EXISTS basis_binding(binding_id TEXT PRIMARY KEY,link_id TEXT NOT NULL,revision INTEGER NOT NULL,generation TEXT NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS basis_binding_lookup ON basis_binding(link_id,revision,generation);
CREATE TABLE IF NOT EXISTS basis_event(event_id TEXT PRIMARY KEY,link_id TEXT NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS basis_receipt(receipt_id TEXT PRIMARY KEY,input_hash TEXT NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS basis_lineage(version_id TEXT PRIMARY KEY,family_id TEXT NOT NULL,payload TEXT NOT NULL,hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS basis_view_head(session_key TEXT PRIMARY KEY,payload TEXT NOT NULL,hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS basis_migration(migration_id TEXT PRIMARY KEY,payload TEXT NOT NULL,hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS basis_document_lookup(link_id TEXT NOT NULL,document_id TEXT NOT NULL,PRIMARY KEY(document_id,link_id));
CREATE TABLE IF NOT EXISTS basis_lookup_version(version INTEGER PRIMARY KEY);
CREATE INDEX IF NOT EXISTS basis_head_team ON basis_head(team_id,link_id);
'''


class Repository:
    def __init__(self,path):
        self.db=connect(path);self.db.row_factory=sqlite3.Row
        self.db.executescript(DDL)
        self.sqlite_document_lookup=True
        with self.transaction():
            if not self.db.execute('SELECT 1 FROM basis_lookup_version WHERE version=1').fetchone():
                # One-time small relation index migration; never reads corpus/index files.
                for table in ('basis_revision','basis_binding'):
                    for row in self.db.execute('SELECT payload,hash FROM '+table):
                        self._index(self.decoded(row))
                self.db.execute('INSERT INTO basis_lookup_version VALUES(1)')

    def _index(self,value):
        if not getattr(self,'sqlite_document_lookup',False):return
        self.db.executemany('INSERT OR IGNORE INTO basis_document_lookup VALUES(?,?)',
                            [(value['link_id'],e['document_id']) for side in ('internal','external') for e in value[side]])

    def links_for_document(self,team,document_id):
        if not getattr(self,'sqlite_document_lookup',False):return self.links(team)
        return [self.decoded(r) for r in self.db.execute(
            'SELECT r.* FROM basis_document_lookup d JOIN basis_head h ON h.link_id=d.link_id '
            'JOIN basis_revision r ON r.link_id=h.link_id AND r.revision=h.revision '
            'WHERE h.team_id=? AND d.document_id=? ORDER BY h.link_id',(team,document_id))]

    def close(self):self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback();raise

    @staticmethod
    def decoded(row):
        if row is None:return None
        value=json.loads(row['payload'])
        require(digest(value)==row['hash'],'BASIS_INTEGRITY','근거 원장 해시가 다릅니다.',409)
        return value

    def head(self,ident):
        row=self.db.execute('SELECT r.* FROM basis_head h JOIN basis_revision r ON r.link_id=h.link_id AND r.revision=h.revision WHERE h.link_id=?',(ident,)).fetchone()
        return self.decoded(row)

    def links(self,team):
        return [self.decoded(r) for r in self.db.execute('SELECT r.* FROM basis_head h JOIN basis_revision r ON r.link_id=h.link_id AND r.revision=h.revision WHERE h.team_id=? ORDER BY h.link_id',(team,))]

    def bindings(self,ident,revision,generation=None):
        sql='SELECT * FROM basis_binding WHERE link_id=? AND revision=?';args=[ident,revision]
        if generation is not None:sql+=' AND generation=?';args.append(generation)
        return [self.decoded(r) for r in self.db.execute(sql+' ORDER BY binding_id',args)]

    def binding(self,ident,revision,generation):
        rows=self.bindings(ident,revision,generation)
        require(len(rows)<=1,'BASIS_BINDING_CONFLICT','같은 세대에 복수 현재 위치가 있습니다.',409)
        return rows[0] if rows else None

    def receipt(self,key,input_hash):
        row=self.db.execute('SELECT * FROM basis_receipt WHERE receipt_id=?',(key,)).fetchone()
        if row is None:return None
        require(row['input_hash']==input_hash,'BASIS_REQUEST_CONFLICT','같은 요청 ID가 다른 내용에 사용되었습니다.',409)
        return self.decoded(row)

    def save_receipt(self,key,input_hash,value):
        self.db.execute('INSERT INTO basis_receipt VALUES(?,?,?,?)',(key,input_hash,encoded(value),digest(value)))

    def append(self,value,event,previous=None):
        ident=value['link_id'];revision=value['revision']
        if previous is None:
            self.db.execute('INSERT INTO basis_head VALUES(?,?,?)',(ident,value['team_id'],revision))
        else:
            n=self.db.execute('UPDATE basis_head SET revision=? WHERE link_id=? AND revision=?',(revision,ident,previous)).rowcount
            require(n==1,'BASIS_STALE_REVISION','다른 사용자가 관계를 변경했습니다.',409)
        self.db.execute('INSERT INTO basis_revision VALUES(?,?,?,?)',(ident,revision,encoded(value),digest(value)))
        self._index(value)
        self.event(event)

    def event(self,value):
        self.db.execute('INSERT INTO basis_event VALUES(?,?,?,?)',(value['event_id'],value['link_id'],encoded(value),digest(value)))

    def put_binding(self,value):
        old=self.binding(value['link_id'],value['link_revision'],value['generation_id'])
        if old:
            require(old==value,'BASIS_BINDING_CONFLICT','게시된 위치는 덮어쓸 수 없습니다.',409);return old
        self.db.execute('INSERT INTO basis_binding VALUES(?,?,?,?,?,?)',(value['binding_id'],value['link_id'],value['link_revision'],value['generation_id'],encoded(value),digest(value)))
        self._index(value)
        return value

    def history(self,ident):
        return {name:[self.decoded(r) for r in self.db.execute('SELECT * FROM '+table+' WHERE link_id=? ORDER BY '+order,(ident,))]
                for name,table,order in [('revisions','basis_revision','revision'),('events','basis_event','event_id'),('bindings','basis_binding','binding_id')]}

    def migration(self,ident):return self.decoded(self.db.execute('SELECT * FROM basis_migration WHERE migration_id=?',(ident,)).fetchone())

    def put_migration(self,value):
        old=self.migration(value['migration_id'])
        require(old is None or old==value,'BASIS_MIGRATION_CONFLICT','이미 저장된 이행 기록과 다릅니다.',409)
        if old is None:self.db.execute('INSERT INTO basis_migration VALUES(?,?,?)',(value['migration_id'],encoded(value),digest(value)))

    def lineage(self,version):return self.decoded(self.db.execute('SELECT * FROM basis_lineage WHERE version_id=?',(version,)).fetchone())

    def register_lineage(self,value):
        from .temporal import validate_lineage
        validate_lineage(value)
        old=self.lineage(value['version_id'])
        require(old is None or old==value,'BASIS_LINEAGE_CONFLICT','판본 계열 기록과 다릅니다.',409)
        if old is None:self.db.execute('INSERT INTO basis_lineage VALUES(?,?,?,?)',(value['version_id'],value['family_id'],encoded(value),digest(value)))

    def view_head(self,key):
        return self.decoded(self.db.execute('SELECT * FROM basis_view_head WHERE session_key=?',(key,)).fetchone())

    def set_view_head(self,key,value):
        if self.view_head(key) is None:self.db.execute('INSERT INTO basis_view_head VALUES(?,?,?)',(key,encoded(value),digest(value)))
        else:self.db.execute('UPDATE basis_view_head SET payload=?,hash=? WHERE session_key=?',(encoded(value),digest(value),key))
