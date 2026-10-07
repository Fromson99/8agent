"""SQL administration state, separate from legal conversations. No Redis or model."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import sqlite3
import time
import uuid

SCHEMA = '''
CREATE TABLE IF NOT EXISTS ad_schema(version INTEGER PRIMARY KEY CHECK(version=1));
INSERT OR IGNORE INTO ad_schema VALUES(1);
CREATE TABLE IF NOT EXISTS ad_session(
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, channel TEXT NOT NULL, chat TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN(0,1)), revision INTEGER NOT NULL DEFAULT 0,
 active_view TEXT, last_operation TEXT, last_job TEXT, pending_action TEXT, pending_field TEXT,
 updated_at REAL NOT NULL, UNIQUE(workspace,channel,chat));
CREATE TABLE IF NOT EXISTS ad_view(
 id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES ad_session(id), kind TEXT NOT NULL,
 position INTEGER NOT NULL DEFAULT 0 CHECK(position>=0), total INTEGER NOT NULL CHECK(total>=0),
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_view_session ON ad_view(session,created_at);
CREATE TABLE IF NOT EXISTS ad_view_row(
 view TEXT NOT NULL REFERENCES ad_view(id), ordinal INTEGER NOT NULL CHECK(ordinal>0),
 kind TEXT NOT NULL, entity TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
 status TEXT NOT NULL, PRIMARY KEY(view,ordinal));
CREATE INDEX IF NOT EXISTS ad_view_entity ON ad_view_row(kind,entity,revision);
CREATE TABLE IF NOT EXISTS ad_selection(
 session TEXT NOT NULL REFERENCES ad_session(id), ordinal INTEGER NOT NULL,
 kind TEXT NOT NULL, entity TEXT NOT NULL, revision INTEGER NOT NULL,
 PRIMARY KEY(session,ordinal));
CREATE TABLE IF NOT EXISTS ad_operation(
 id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES ad_session(id), request TEXT NOT NULL,
 input_hash TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN('RUNNING','SUCCEEDED','FAILED')),
 created_at REAL NOT NULL, finished_at REAL, response TEXT,
 UNIQUE(session,request));
CREATE INDEX IF NOT EXISTS ad_operation_session ON ad_operation(session,created_at);
CREATE TABLE IF NOT EXISTS ad_change(
 operation TEXT NOT NULL REFERENCES ad_operation(id), ordinal INTEGER NOT NULL,
 kind TEXT NOT NULL, entity TEXT NOT NULL, before_revision INTEGER NOT NULL,
 after_revision INTEGER NOT NULL, action TEXT NOT NULL, field TEXT, before_value TEXT, after_value TEXT,
 PRIMARY KEY(operation,ordinal));
CREATE INDEX IF NOT EXISTS ad_change_entity ON ad_change(kind,entity,operation);
CREATE TABLE IF NOT EXISTS ad_object(
 kind TEXT NOT NULL, entity TEXT NOT NULL, workspace TEXT NOT NULL,
 review TEXT NOT NULL DEFAULT 'PENDING' CHECK(review IN('PENDING','APPROVED','REJECTED')),
 reviewed_revision INTEGER, trashed INTEGER NOT NULL DEFAULT 0 CHECK(trashed IN(0,1)),
 revision INTEGER NOT NULL DEFAULT 0, changed_at REAL NOT NULL,
 PRIMARY KEY(kind,entity));
CREATE INDEX IF NOT EXISTS ad_object_status ON ad_object(workspace,trashed,review,kind,entity);
CREATE TABLE IF NOT EXISTS ad_feature(
 workspace TEXT PRIMARY KEY, shortcut INTEGER NOT NULL DEFAULT 1 CHECK(shortcut IN(0,1)),
 wiki INTEGER NOT NULL DEFAULT 1 CHECK(wiki IN(0,1)), revision INTEGER NOT NULL DEFAULT 0,
 changed_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ad_schedule(
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, session TEXT NOT NULL REFERENCES ad_session(id),
 due_at REAL NOT NULL, timezone TEXT NOT NULL DEFAULT 'Asia/Seoul',
 repeat_seconds INTEGER NOT NULL DEFAULT 0 CHECK(repeat_seconds IN(0,86400)),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN(0,1)), last_due_at REAL,
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_schedule_due ON ad_schedule(enabled,due_at);
CREATE TABLE IF NOT EXISTS ad_job(
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, session TEXT NOT NULL REFERENCES ad_session(id),
 schedule TEXT REFERENCES ad_schedule(id), scheduled_for REAL,
 status TEXT NOT NULL CHECK(status IN('QUEUED','RUNNING','PAUSED','CANCELLED','SUCCEEDED','FAILED','PARTIAL')),
 desired TEXT NOT NULL DEFAULT 'RUN' CHECK(desired IN('RUN','PAUSE','CANCEL')),
 created_at REAL NOT NULL, started_at REAL, finished_at REAL, heartbeat REAL,
 lease TEXT, lease_until REAL, completed INTEGER NOT NULL DEFAULT 0,
 failed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
 UNIQUE(schedule,scheduled_for));
CREATE INDEX IF NOT EXISTS ad_job_ready ON ad_job(status,created_at);
CREATE INDEX IF NOT EXISTS ad_job_workspace ON ad_job(workspace,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS ad_job_one_running ON ad_job(workspace) WHERE status='RUNNING';
CREATE TABLE IF NOT EXISTS ad_job_item(
 job TEXT NOT NULL REFERENCES ad_job(id), queue_id INTEGER NOT NULL, scope TEXT NOT NULL,
 investigation TEXT NOT NULL, revision INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN('PENDING','RUNNING','DONE','FAILED')), attempts INTEGER NOT NULL DEFAULT 0,
 started_at REAL, finished_at REAL, detail TEXT,
 PRIMARY KEY(job,queue_id));
CREATE INDEX IF NOT EXISTS ad_job_item_ready ON ad_job_item(job,status,queue_id);
CREATE TABLE IF NOT EXISTS ad_error(
 id TEXT PRIMARY KEY, session TEXT REFERENCES ad_session(id), job TEXT REFERENCES ad_job(id),
 operation TEXT REFERENCES ad_operation(id), stage TEXT NOT NULL, error_type TEXT NOT NULL,
 message TEXT NOT NULL, detail TEXT NOT NULL, retryable INTEGER NOT NULL CHECK(retryable IN(0,1)),
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_error_session ON ad_error(session,created_at);
CREATE INDEX IF NOT EXISTS ad_error_job ON ad_error(job,created_at);
CREATE TABLE IF NOT EXISTS ad_exclusion(
 workspace TEXT NOT NULL, unit TEXT NOT NULL, signature TEXT NOT NULL,
 active INTEGER NOT NULL CHECK(active IN(0,1)), PRIMARY KEY(workspace,unit));
CREATE INDEX IF NOT EXISTS ad_exclusion_input ON ad_exclusion(workspace,signature,active);
CREATE TABLE IF NOT EXISTS ad_wiki_index(
 unit TEXT PRIMARY KEY, workspace TEXT NOT NULL, revision INTEGER NOT NULL,
 topic TEXT NOT NULL, question TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ad_wiki_topic ON ad_wiki_index(workspace,topic,unit);
CREATE TABLE IF NOT EXISTS ad_worker(id TEXT PRIMARY KEY, pid INTEGER NOT NULL, heartbeat REAL NOT NULL, status TEXT NOT NULL CHECK(status IN('POLLING','FAILED')), error TEXT);
CREATE TABLE IF NOT EXISTS ad_detail(
 id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES ad_session(id),
 entity TEXT NOT NULL, content TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_detail_session ON ad_detail(session,created_at);
CREATE TABLE IF NOT EXISTS ad_language_turn(
 operation TEXT PRIMARY KEY REFERENCES ad_operation(id), session TEXT NOT NULL REFERENCES ad_session(id),
 context_hash TEXT NOT NULL, input TEXT NOT NULL, model_output TEXT, plan TEXT, receipt TEXT,
 lease_until REAL NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ad_language_session ON ad_language_turn(session,created_at);
CREATE TABLE IF NOT EXISTS ad_language_call(
 operation TEXT NOT NULL REFERENCES ad_language_turn(operation), sequence INTEGER NOT NULL,
 input TEXT NOT NULL, model_output TEXT, plan TEXT, receipt TEXT, created_at REAL NOT NULL,
 PRIMARY KEY(operation,sequence));
'''


def ident(prefix):
    return prefix + uuid.uuid4().hex[:16]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        from .state_sqlite import connect
        self.db = connect(self.path)
        self.db.row_factory = sqlite3.Row
        if table_exists(self.db,'ad_schema') and {r[0] for r in self.db.execute('SELECT version FROM ad_schema')}!={1}:
            self.db.close();raise ValueError('AD_SCHEMA_VERSION: unsupported administration schema; restore matching code or migrate explicitly')
        self.db.executescript(SCHEMA)
        self.path.chmod(0o600)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        nested = self.db.in_transaction
        if not nested:self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            if not nested:self.db.execute('COMMIT')
        except BaseException:
            if not nested:self.db.execute('ROLLBACK')
            raise

    def session(self, workspace, channel, chat):
        if not chat or chat=='sess-anonymous':
            raise ValueError('AD_SESSION: stable GENOS chatId/session_id required')
        key = fingerprint([workspace,channel,chat])
        self.db.execute('INSERT OR IGNORE INTO ad_session(id,workspace,channel,chat,updated_at) VALUES(?,?,?,?,?)',
                        (key,workspace,channel,chat,time.time()))
        self.db.execute('INSERT OR IGNORE INTO ad_feature(workspace,changed_at) VALUES(?,?)',(workspace,time.time()))
        return dict(self.db.execute('SELECT * FROM ad_session WHERE id=?',(key,)).fetchone())

    def view(self, session, kind, rows):
        key=ident('V')
        self.db.execute('INSERT INTO ad_view(id,session,kind,total,created_at) VALUES(?,?,?,?,?)',
                        (key,session,kind,len(rows),time.time()))
        self.db.executemany('INSERT INTO ad_view_row VALUES(?,?,?,?,?,?,?)',
            [(key,i+1,r['kind'],str(r['id']),int(r.get('revision',0)),str(r.get('title','')),str(r.get('status',''))) for i,r in enumerate(rows)])
        self.db.execute('UPDATE ad_session SET active_view=?,revision=revision+1,updated_at=? WHERE id=?',(key,time.time(),session))
        self.db.execute('DELETE FROM ad_selection WHERE session=?',(session,))
        return key

    def page(self, session, view=None, *, previous=False, size=20):
        view=view or self.db.execute('SELECT active_view FROM ad_session WHERE id=?',(session,)).fetchone()[0]
        v=self.db.execute('SELECT * FROM ad_view WHERE id=? AND session=?',(view,session)).fetchone()
        if not v:raise ValueError('AD_VIEW: 이전 표가 없습니다. 목록을 먼저 조회하세요.')
        start=max(0,v['position']-2*size) if previous else v['position']
        rows=[dict(r) for r in self.db.execute('SELECT * FROM ad_view_row WHERE view=? AND ordinal>? ORDER BY ordinal LIMIT ?',(view,start,size))]
        position=rows[-1]['ordinal'] if rows else start
        self.db.execute('UPDATE ad_view SET position=? WHERE id=?',(position,view))
        return {'view_id':view,'rows':rows,'total':v['total'],'position':position,'has_more':position<v['total']}


def table_exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None


def features(db, workspace):
    if not table_exists(db,'ad_feature'):return {'shortcut':True,'wiki':True,'revision':0}
    row=db.execute('SELECT shortcut,wiki,revision FROM ad_feature WHERE workspace=?',(workspace,)).fetchone()
    return dict(zip(('shortcut','wiki','revision'),row)) if row else {'shortcut':True,'wiki':True,'revision':0}


def excluded(db, kind, entity, *, revision=None):
    if not table_exists(db,'ad_object'):return False
    row=db.execute('SELECT trashed,review,reviewed_revision FROM ad_object WHERE kind=? AND entity=?',(kind,str(entity))).fetchone()
    return bool(row and (row[0] or row[1]=='REJECTED' or (revision is not None and row[1]=='APPROVED' and row[2]!=revision)))
