"""Lossless glossary evidence transport and bounded resumable row writing."""
import base64
import gzip
import hashlib
import json
import sqlite3

import pytest
from test_compact_v2_rag import structured_generation
from lawrag.pipeline import oracle_query_package as pack, oracle_query_publish as pub
from semantic_runtime import oracle_dp_io as io


@pytest.mark.parametrize('raw', [None, b'', b'\x00\xff\x80', gzip.compress('한글 응답'.encode(),mtime=0)])
def test_known_response_roundtrips_exact_bytes_and_declares_encoding(tmp_path,raw):
    path=tmp_path/'dictionary.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE source_request(id TEXT PRIMARY KEY,response BLOB,response_sha256 TEXT)')
        db.execute('INSERT INTO source_request VALUES(?,?,?)',('r1',raw,'unchanged-source-hash'))
    before=io.file_sha(path)
    rows=list(pub.asset_rows(path,'glossary/dictionary.sqlite'))
    assert len(rows)==1
    encoded=rows[0]['value']['response']
    assert (None if encoded is None else base64.b64decode(encoded,validate=True))==raw
    assert rows[0]['value']['response_sha256']=='unchanged-source-hash'
    spec=next(iter(pub.asset_schema(path,'glossary/dictionary.sqlite').values()))
    pub._column_shapes(spec,rows[0]['value'])
    assert spec['columns']['response']['transport_encoding']=='base64-v1'
    assert spec['columns']['response']['source_storage']=='blob'
    assert io.file_sha(path)==before


@pytest.mark.parametrize('table,column,value,error',[
    ('other','response',b'raw','QUERY_EXPORT_BLOB'),
    ('source_request','unexpected',b'raw','QUERY_EXPORT_BLOB'),
    ('source_request','response','not binary','QUERY_EXPORT_BINARY_TYPE'),
])
def test_unknown_binary_and_mistyped_response_remain_errors(tmp_path,table,column,value,error):
    path=tmp_path/'bad.sqlite'
    with sqlite3.connect(path) as db:
        db.execute(f'CREATE TABLE {table}(id TEXT PRIMARY KEY,{column} BLOB)')
        db.execute(f'INSERT INTO {table} VALUES(?,?)',('r1',value))
    with pytest.raises(io.DPError,match=error):list(pub.asset_rows(path,'bad.sqlite'))


def test_database_only_uses_one_prefix_select_and_never_compresses(structured_generation,tmp_path,monkeypatch):
    folder=tmp_path/'out';statements=[];connect=sqlite3.connect
    def traced(path,*args,**kw):
        db=connect(path,*args,**kw)
        if str(path).endswith('.partial'):db.set_trace_callback(statements.append)
        return db
    monkeypatch.setattr(pack.sqlite3,'connect',traced)
    monkeypatch.setattr(pack,'split_db',lambda *a,**kw:pytest.fail('unused ZIP'))
    monkeypatch.setattr(pack,'split_db_direct',lambda *a,**kw:pytest.fail('unused parts'))
    first=pack.export(structured_generation,folder,database_only=True)
    assert first['db_sha256']==io.file_sha(folder/pack.DB_NAME)
    assert first['db_bytes']==(folder/pack.DB_NAME).stat().st_size
    assert not (folder/'download').exists() and not (folder/'query-data.zip').exists()
    assert pack.verify_db(folder/pack.DB_NAME)
    prefix=[s for s in statements if s.startswith('SELECT seq,kind,row_id,body FROM query_row WHERE seq<=')]
    assert len(prefix)==1
    assert not any('WHERE seq=' in s for s in statements)
    deadline=pack.bounded_json(folder/'export-state.json')['deadline']
    assert pack.export(structured_generation,folder,database_only=True)==first
    assert pack.bounded_json(folder/'export-state.json')['deadline']==deadline


@pytest.mark.parametrize('tamper',[False,True])
def test_prefix_recheck_preserves_deadline_and_rejects_conflict(structured_generation,tmp_path,monkeypatch,tamper):
    folder=tmp_path/'resume';original=pub.projected_rows
    def stop(path,relative,source):
        if relative!='store.sqlite':raise io.DPError('INJECTED_AFTER_COMMITTED_SOURCE')
        yield from original(path,relative,source)
    monkeypatch.setattr(pub,'projected_rows',stop)
    with pytest.raises(io.DPError,match='INJECTED'):pack.export(structured_generation,folder,database_only=True)
    deadline=pack.bounded_json(folder/'export-state.json')['deadline']
    with sqlite3.connect(folder/(pack.DB_NAME+'.partial')) as db:
        before=db.execute('SELECT * FROM query_row ORDER BY seq').fetchall()
        assert before
        if tamper:db.execute("UPDATE query_row SET body='{}' WHERE seq=1")
    monkeypatch.setattr(pub,'projected_rows',original)
    if tamper:
        with pytest.raises(io.DPError,match='EXPORT_RESUME_CONFLICT'):pack.export(structured_generation,folder,database_only=True)
        assert not (folder/pack.DB_NAME).exists()
    else:
        pack.export(structured_generation,folder,database_only=True)
        with sqlite3.connect(folder/pack.DB_NAME) as db:
            assert db.execute('SELECT * FROM query_row WHERE seq<=? ORDER BY seq',(len(before),)).fetchall()==before
    assert pack.bounded_json(folder/'export-state.json')['deadline']==deadline


def test_incompatible_packaging_rejected_before_work(tmp_path):
    with pytest.raises(io.DPError,match='EXPORT_PACKAGING'):
        pack.export(tmp_path/'absent',tmp_path/'out',direct_parts=True,database_only=True)
    assert not (tmp_path/'out').exists()
