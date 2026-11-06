"""Portable, reviewed snapshot handoff. No model or external credentials."""
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE/'payload'
CONFIG_PATH = '02_BACKEND/semantic_runtime/ontology_work/configuration.py'
OLD_CONFIG_SHA = '291e20322f9c1a1c3bcdf32bec44f451266df178c2e97ca53fb7feafd4b6dfda'
TABLES = {'work':'LGL_ONT_WORK_A', 'event':'LGL_ONT_EVT_A', 'publication':'LGL_ONT_PUB_A',
          'head':'LGL_ONT_HEAD_A', 'anchor':'LGL_ONT_ANC_A'}

def sha(raw): return hashlib.sha256(raw).hexdigest()
def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()
def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def json_bytes(value): return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

def verify_package():
    checks = read_json(HERE/'PACKAGE_MANIFEST.json')['files']
    for name, expected in checks.items():
        p = HERE/name
        if p.is_symlink() or sha(p.read_bytes()) != expected:
            raise ValueError('Package changed: '+name)
    return read_json(PAYLOAD/'sources.json')

def verify_sources(read):
    sources = read_json(PAYLOAD/'sources.json')
    for item in sources:
        a = item['anchor']; version, blocks = read(a)
        if version != a['version'] or [str(b[0]) for b in blocks] != item['block_ids']:
            raise ValueError('Source version/extent mismatch: '+a['document_id']+'/'+a['unit_id'])
        if sha('\n'.join(b[1] for b in blocks).encode()) != a['content_sha256']:
            raise ValueError('Source text mismatch: '+a['document_id']+'/'+a['unit_id'])
    return len(sources)

def sqlite_sources(source):
    with closing(sqlite3.connect(Path(source).as_uri()+'?mode=ro',uri=True)) as db:
        def read(a):
            row=db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(a['document_id'],)).fetchone()
            blocks=db.execute('SELECT block_id,text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',
                              (a['document_id'],a['unit_id'])).fetchmany(4097)
            return (row[0] if row else None), blocks
        return verify_sources(read)

def inventory():return read_json(PAYLOAD/'inventory.json')

def snapshot():
    with closing(sqlite3.connect((PAYLOAD/'ontology.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Snapshot integrity')
        cols={k:[r[1] for r in db.execute('PRAGMA table_info('+t+')')] for k,t in TABLES.items()}
        rows={k:[dict(zip(cols[k],r)) for r in db.execute('SELECT * FROM '+t)] for k,t in TABLES.items()}
    expected=read_json(PAYLOAD/'inventory.json')['table_counts']
    if {k:len(rows[k]) for k in TABLES} != expected:
        raise ValueError('Snapshot counts')
    return cols, rows

def patched_config(old):
    if sha(old) != OLD_CONFIG_SHA:
        raise ValueError('Unsupported existing configuration.py; preserve current code and inspect compatibility')
    needle="    cfg=config or settings();db=cfg['database'];kind=db['kind']\n"
    source=old.decode()
    if source.count(needle)!=1: raise ValueError('Patch anchor')
    source=source.replace(needle,needle+"    if kind=='sqlite-published':return _published_sqlite(cfg)\n")
    return (source+(HERE/'published_reader.txt').read_text()).encode()
