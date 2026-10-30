"""Offline physical projections. Native documents and build evidence stay in audit.

Version 2 document.json is metadata only; native source_unit and source_block
remain lossless. The source_block view restores its former JSON contract lazily.
Navigation exposes the same logical relations over integer occurrence keys.
"""
from contextlib import closing
from pathlib import Path
import os
import sqlite3
from .contracts import sha, write


def source(generation, audit_directory, manifest):
    generation, audit = Path(generation), Path(audit_directory)
    original = generation/'store.sqlite'
    if original.stat().st_nlink != 1 or audit.exists():
        raise ValueError('compact source requires a new unshared output')
    audit.mkdir(parents=True)
    cold = audit/'store.sqlite'
    os.rename(original, cold)
    try:
        with closing(sqlite3.connect(original)) as db:
            db.execute('ATTACH DATABASE ? AS raw', (cold.resolve().as_uri()+'?mode=ro',))
            columns=[r[1] for r in db.execute('PRAGMA raw.table_info(document)')]
            fields=','.join("json_remove(json,'$.nodes','$.blocks') AS json" if c=='json' else '"'+c+'"' for c in columns)
            db.execute('CREATE TABLE document AS SELECT '+fields+' FROM raw.document')
            db.execute('CREATE UNIQUE INDEX document_pk ON document(document_id)')
            db.execute('CREATE TABLE source_unit AS SELECT * FROM raw.source_unit')
            db.execute('CREATE UNIQUE INDEX unit_pk ON source_unit(document_id,unit_id)')
            columns=[r[1] for r in db.execute('PRAGMA raw.table_info(source_block)')]
            fields=','.join("CASE WHEN json_extract(json,'$.text') IS text THEN json_remove(json,'$.text') ELSE json END AS json" if c=='json' else '"'+c+'"' for c in columns)
            db.execute("CREATE TABLE block_payload AS SELECT "+fields+", (json_type(json,'$.text')='text' AND json_extract(json,'$.text') IS text) AS json_text_elided FROM raw.source_block")
            db.execute('CREATE UNIQUE INDEX block_pk ON block_payload(document_id,block_id)')
            db.execute('CREATE INDEX block_range ON block_payload(document_id,CAST(block_id AS INTEGER))')
            db.execute('CREATE INDEX block_owner ON block_payload(document_id,unit_id,CAST(block_id AS INTEGER))')
            fields=','.join("CASE WHEN json_text_elided THEN json_set(json,'$.text',text) ELSE json END AS json" if c=='json' else '"'+c+'"' for c in columns)
            db.execute('CREATE VIEW source_block AS SELECT '+fields+' FROM block_payload')
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('compact source integrity failed')
            counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('document','source_unit','source_block')}
            if counts != manifest['counts']:raise ValueError('compact source count drift')
        original_hash=sha(cold)
        receipt={'schema_version':'source-storage-projection-v2','native_store_sha256':original_hash,
                 'native_store_file':'store.sqlite','native_bytes':cold.stat().st_size,
                 'serving_store_sha256':sha(original),'serving_bytes':original.stat().st_size,
                 'document_json':'metadata-without-nodes-and-blocks','unit_and_block_contract':'lossless',
                 'counts':counts,'compiler_sha256':sha(__file__)}
        write(audit/'manifest.json',receipt)
        return {**manifest,'schema_version':'term-source-generation-v2',
                'store_sha256':receipt['serving_store_sha256'],
                'source_storage':{'schema_version':'source-storage-projection-v2',
                    'audit_manifest_sha256':sha(audit/'manifest.json'),'native_store_sha256':original_hash,
                    'document_json':'metadata-without-nodes-and-blocks'}}
    except BaseException:
        original.unlink(missing_ok=True)
        os.rename(cold,original)
        raise


def occurrence_projection(db):
    """Copy integers directly from the audit, avoiding a second TEXT occurrence copy."""
    if db.execute('SELECT 1 FROM construction.occurrence o LEFT JOIN term t ON t.id=o.term_id LEFT JOIN source s ON s.id=o.source_id WHERE t.id IS NULL OR s.id IS NULL LIMIT 1').fetchone():
        raise ValueError('occurrence points outside navigation catalogues')
    expected=db.execute('SELECT count(*) FROM construction.occurrence').fetchone()[0]
    db.execute('CREATE TABLE occurrence_keys(term_key INTEGER NOT NULL,source_key INTEGER NOT NULL,PRIMARY KEY(term_key,source_key)) WITHOUT ROWID')
    db.execute('INSERT INTO occurrence_keys SELECT t.rowid,s.rowid FROM construction.occurrence o JOIN term t ON t.id=o.term_id JOIN source s ON s.id=o.source_id')
    db.execute('CREATE INDEX occurrence_keys_source ON occurrence_keys(source_key,term_key)')
    if db.execute('SELECT count(*) FROM occurrence_keys').fetchone()[0]!=expected:
        raise ValueError('occurrence projection count mismatch')
    db.execute('CREATE VIEW occurrence AS SELECT t.id AS term_id,s.id AS source_id FROM occurrence_keys o JOIN term t ON t.rowid=o.term_key JOIN source s ON s.rowid=o.source_key')


def verify_source_audit(directory, binding, expected_store_sha256):
    import json
    directory=Path(directory)
    if sha(directory/'manifest.json')!=binding['audit_manifest_sha256']:
        raise ValueError('source audit manifest drift')
    m=json.loads((directory/'manifest.json').read_text())
    if (m.get('schema_version')!='source-storage-projection-v2' or
        m['native_store_sha256']!=binding['native_store_sha256'] or
        m['serving_store_sha256']!=expected_store_sha256 or
        sha(directory/'store.sqlite')!=m['native_store_sha256']):
        raise ValueError('source audit binding drift')
    return m
