"""Unpublished compact-v2 navigation: direct audit and transactional checkpoints."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
from .contracts import sha,write
from .navigation_storage import AUDIT_TABLES,_tables


class AuditSQL:
    """Qualify this module's fixed construction SQL, including index DDL.

    Values are always bound parameters; this is not an arbitrary SQL router.
    Both databases use DELETE journals and FULL sync on the same filesystem.
    SQLite's super-journal then commits document rows and receipts together.
    """
    def __init__(self, db):self.db=db
    @staticmethod
    def qualify(sql):
        for name in AUDIT_TABLES:
            sql=re.sub(r'(?<![\w.])'+name+r'\b','construction.'+name,sql)
        sql=re.sub(r'(CREATE (?:UNIQUE )?INDEX )(\w+)( ON )construction\.(\w+)',
                   r'\1construction.\2\3\4',sql,flags=re.I)
        return sql
    def execute(self,sql,*args):return self.db.execute(self.qualify(sql),*args)
    def executemany(self,sql,*args):return self.db.executemany(self.qualify(sql),*args)
    def executescript(self,sql):
        # Only LinkProjector's static table/index DDL uses this method.
        for statement in sql.split(';'):
            if statement.strip():self.execute(statement)


def get(db, stage, item=''):
    row=db.execute('SELECT json FROM navigation_checkpoint WHERE stage=? AND item=?',(stage,item)).fetchone()
    return json.loads(row[0]) if row else None


def put(db,stage,value,item=''):
    db.execute('INSERT OR REPLACE INTO navigation_checkpoint VALUES (?,?,?)',(stage,item,json.dumps(value)))


def open_build(output,audit,identity):
    output,audit=Path(output),Path(audit)
    output.mkdir(parents=True,exist_ok=True);audit.mkdir(parents=True,exist_ok=True)
    if output.stat().st_dev!=audit.stat().st_dev:raise ValueError('checkpoint audit must share filesystem')
    pin=output/'build-identity.json'
    if pin.exists():
        if json.loads(pin.read_text())!=identity:raise ValueError('navigation resume identity changed')
    else:
        if any(output.iterdir()) or any(audit.iterdir()):raise ValueError('unowned partial navigation')
        write(pin,identity)
    db=sqlite3.connect(output/'navigation.sqlite');db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
    db.execute('ATTACH DATABASE ? AS construction',(str(audit/'navigation.sqlite'),))
    db.execute('PRAGMA construction.journal_mode=DELETE');db.execute('PRAGMA construction.synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS navigation_checkpoint(stage TEXT,item TEXT,json TEXT,PRIMARY KEY(stage,item))')
    # An uncompleted initial schema/catalogue has no document checkpoints.
    if get(db,'initialized') is None:
        for schema in ('main','construction'):
            for kind,name in list(db.execute(f"SELECT type,name FROM {schema}.sqlite_master WHERE type IN ('trigger','view','table') AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'trigger' THEN 0 WHEN 'view' THEN 1 ELSE 2 END")):
                if name=='navigation_checkpoint':continue
                db.execute(f'DROP {kind} {schema}."{name}"')
        db.commit()
    return db


def occurrence_schema(db):
    db.execute('DROP TABLE occurrence')
    db.executescript('''
      CREATE TABLE occurrence_keys(term_key INTEGER NOT NULL,source_key INTEGER NOT NULL,
        PRIMARY KEY(term_key,source_key)) WITHOUT ROWID;
      CREATE INDEX occurrence_keys_source ON occurrence_keys(source_key,term_key);
      CREATE VIEW occurrence AS SELECT t.id AS term_id,s.id AS source_id FROM occurrence_keys o
        JOIN term t ON t.rowid=o.term_key JOIN source s ON s.rowid=o.source_key;
      CREATE TRIGGER occurrence_insert INSTEAD OF INSERT ON occurrence BEGIN
        SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM term WHERE id=NEW.term_id)
          OR NOT EXISTS(SELECT 1 FROM source WHERE id=NEW.source_id) THEN RAISE(ABORT,'unknown occurrence coordinate') END;
        INSERT INTO occurrence_keys VALUES((SELECT rowid FROM term WHERE id=NEW.term_id),(SELECT rowid FROM source WHERE id=NEW.source_id));
      END;
      CREATE TRIGGER occurrence_delete INSTEAD OF DELETE ON occurrence BEGIN
        DELETE FROM occurrence_keys WHERE term_key=(SELECT rowid FROM term WHERE id=OLD.term_id)
          AND source_key=(SELECT rowid FROM source WHERE id=OLD.source_id);
      END;
    ''')


def finish_audit(index,audit):
    index,audit=Path(index),Path(audit)
    with closing(sqlite3.connect(index)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('runtime integrity')
        tables=sorted(_tables(db))
        views=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
    with closing(sqlite3.connect(audit/'navigation.sqlite')) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('audit integrity')
        if _tables(db)!=set(AUDIT_TABLES):raise ValueError('construction coverage')
        counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in AUDIT_TABLES}
    manifest={'schema_version':'term-navigation-storage-v3','audit_policy':'logical-construction-evidence',
              'audit_file':'navigation.sqlite','audit_sha256':sha(audit/'navigation.sqlite'),
              'audit_bytes':(audit/'navigation.sqlite').stat().st_size,'serving_index_sha256':sha(index),
              'serving_index_bytes':index.stat().st_size,'construction_tables':counts,
              'runtime_tables':tables,'runtime_views':views,'compiler_sha256':sha(__file__),
              'llm_calls':0,'separation_strategy':'direct-attached-audit'}
    path=audit/'manifest.json'
    if path.exists():
        if json.loads(path.read_text())!=manifest:raise ValueError('completed audit manifest drift')
    else:write(path,manifest)
    return {'schema_version':manifest['schema_version'],'mode':'separate-build-audit',
            'audit_manifest_sha256':sha(path),'construction_tables':list(AUDIT_TABLES)}
