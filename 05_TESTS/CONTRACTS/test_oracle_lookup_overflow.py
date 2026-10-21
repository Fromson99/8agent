"""Long auxiliary keys retain source values and exact, scoped SQL equality."""
import ast
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from lawrag.pipeline import oracle_query_publish as pub, oracle_clean_import as clean
from semantic_runtime import oracle_query_catalog as q, oracle_dp_io as io
from semantic_runtime.oracle_query_db import Connection
from test_compact_v2_rag import structured_generation
from test_oracle_full_package import full
from test_oracle_clean_import import setup, Database

ROOT = Path(__file__).resolve().parents[2]
R1 = ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_clean_import_20261020_r1/package'


def fixture_rows(tmp_path, field, value):
    path = tmp_path/'keys.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sample(document_id TEXT,id TEXT,source_id TEXT,target TEXT)')
        db.execute('INSERT INTO sample VALUES(?,?,?,?)',
                   tuple({'document_id':'allowed','id':'short','source_id':'owner','target':'target',field:value}[k]
                         for k in ('document_id','id','source_id','target')))
    before = io.file_sha(path)
    rows = list(pub.asset_rows(path,'sample.sqlite'))
    tables = pub.asset_schema(path,'sample.sqlite')
    for row in rows:
        pub._column_shapes(tables[row['kind']],row['value'])
    assert io.file_sha(path) == before
    return rows,tables


@pytest.mark.parametrize('field,physical',[('id','lookup_id'),('source_id','owner_id'),('target','target_id')])
@pytest.mark.parametrize('value',['x'*512,'x'*513,'가'*171,'😀'*129,"한글'😀"*700])
def test_projection_and_real_sql_compiler_preserve_original(tmp_path,field,physical,value):
    rows,tables = fixture_rows(tmp_path,field,value)
    assert rows[0]['value'][field] == value
    assert rows[0][physical] == q.lookup_key(value)
    assert len(rows[0][physical].encode()) <= 512
    assert rows[0]['row_id'] == io.digest([0,rows[0]['value']])
    captured = []
    class SQL:
        def query(self,statement,binds,limit):
            captured.append((statement,binds))
            # Assert the actual service SQL retains BOTH candidate and logical
            # predicates, not only a lossy prefix/hash. No Oracle engine claim.
            assert physical.upper() in statement
            assert 'r.DOCUMENT_ID IS NULL OR r.DOCUMENT_ID IN' in statement
            assert '"sample"."'+field+'"' in statement
            values = {n:v for n,v,_ in binds}
            assert values['a8_p0'] == value
            assert any(json.loads(v) == ['allowed'] for n,v,t in binds if n.startswith('a8_scope'))
            if len(value.encode()) > 512:
                assert [v for n,v,t in binds if n.startswith('a8_index_key')] == [q.lookup_key(value)]
            if len(value.encode()) > 4000:
                assert 'DBMS_LOB.COMPARE' in statement
                assert ('a8_p0',value,'CLOB') in binds
            return [{'BODY':json.dumps([value],ensure_ascii=False),'N':io.units(json.dumps([value],ensure_ascii=False))}]
    request = SimpleNamespace(sql=SQL(),release_id='a'*64,sources=SimpleNamespace(allowed={'allowed'}),
                              records=SimpleNamespace(manifest={'tables':tables}))
    port = Connection(request,'sample.sqlite')
    assert port.execute('SELECT '+field+' FROM sample WHERE '+field+'=?',(value,)).fetchone()[0] == value
    assert len(captured) == 1


def test_same_prefix_and_hash_lookalike_still_require_original_equality(tmp_path):
    a,b = '가'*171+'a','가'*171+'b'
    assert q.lookup_key(a) != q.lookup_key(b)
    literal = q.lookup_key(a)
    assert q.lookup_key(literal) == literal  # intentional candidate collision
    rows,tables = fixture_rows(tmp_path,'id',a)
    calls=[]
    request=SimpleNamespace(sql=None,release_id='a'*64,sources=SimpleNamespace(allowed={'allowed'}),
                            records=SimpleNamespace(manifest={'tables':tables}))
    port=Connection(request,'sample.sqlite')
    port._pages=lambda statement,binds:(calls.append((statement,binds)) or iter([]))
    for value in (a,b,literal):
        list(port.execute('SELECT id FROM sample WHERE id=?',(value,)))
        statement,binds=calls[-1]
        assert '"sample"."id" = :a8_p0' in statement
        assert ('a8_p0',value,'VARCHAR2') in binds


def test_long_literal_uses_bounded_index_and_clob_original(tmp_path):
    value="긴'값"*1500
    _,tables=fixture_rows(tmp_path,'target',value)
    request=SimpleNamespace(sql=None,release_id='a'*64,sources=SimpleNamespace(allowed={'allowed'}),
                            records=SimpleNamespace(manifest={'tables':tables}))
    port=Connection(request,'sample.sqlite');calls=[]
    port._pages=lambda statement,binds:(calls.append((statement,binds)) or iter([]))
    list(port.execute("SELECT target FROM sample WHERE target='"+value.replace("'","''")+"'"))
    statement,binds=calls[0]
    assert value not in statement and 'DBMS_LOB.COMPARE' in statement
    assert any(v==value and t=='CLOB' for n,v,t in binds)
    assert any(v==q.lookup_key(value) and t=='VARCHAR2' for n,v,t in binds)


def test_long_query_against_short_column_still_uses_lob_equality(tmp_path):
    _,tables=fixture_rows(tmp_path,'id','short')
    request=SimpleNamespace(sql=None,release_id='a'*64,sources=SimpleNamespace(allowed={'allowed'}),
                            records=SimpleNamespace(manifest={'tables':tables}))
    port=Connection(request,'sample.sqlite');calls=[]
    port._pages=lambda statement,binds:(calls.append((statement,binds)) or iter([]))
    assert list(port.execute('SELECT id FROM sample WHERE id=?',('가'*1500,)))==[]
    assert 'DBMS_LOB.COMPARE' in calls[0][0]


def test_document_scope_is_never_hashed_or_silently_dropped(tmp_path):
    with pytest.raises(io.DPError,match=r'field=document_id utf8_bytes=513.*asset=sample.sqlite table=sample'):
        fixture_rows(tmp_path,'document_id','가'*171)


def test_unknown_encoding_rejected_and_legacy_short_predicate_unchanged(tmp_path):
    _,tables=fixture_rows(tmp_path,'id','short')
    table=next(iter(tables.values()))
    request=SimpleNamespace(sql=None,release_id='a'*64,sources=SimpleNamespace(allowed={'allowed'}),
                            records=SimpleNamespace(manifest={'tables':tables}))
    port=Connection(request,'sample.sqlite');calls=[]
    port._pages=lambda statement,binds:(calls.append((statement,binds)) or iter([]))
    table.pop('lookup_encoding')
    list(port.execute('SELECT id FROM sample WHERE id=?',('short',)))
    assert 'r.LOOKUP_ID = :a8_p0' in calls[0][0]
    assert not any(n.startswith('a8_index') for n,v,t in calls[0][1])
    table['lookup_encoding']='unknown'
    with pytest.raises(io.DPError,match='QUERY_LOOKUP_ENCODING'):
        port.execute('SELECT id FROM sample WHERE id=?',('short',))


@pytest.fixture
def failed_r1(structured_generation,tmp_path):
    # Modify only this synthetic fixture, then publish a fresh transport with
    # correct hashes. Never rewrite a production manifest to bypass a mismatch.
    generation=structured_generation
    path=generation/'fulltext/units.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE overflow_sample(id TEXT,target TEXT)')
        db.execute('INSERT INTO overflow_sample VALUES(?,?)',('long-key','가'*171))
    fm=io.file_sha
    meta=path.with_name('manifest.json');body=json.loads(meta.read_text())
    body['index_sha256']=fm(path);io.atomic_json(meta,body)
    manifest=generation/'manifest.json';body=json.loads(manifest.read_text())
    body['fulltext']['manifest_sha256']=fm(meta);io.atomic_json(manifest,body)
    data=full.__wrapped__(generation,tmp_path)
    db,work=setup.__wrapped__(data,tmp_path)
    from test_oracle_deferred_indexes import _mock_code
    source=Path(__file__).with_name('test_oracle_clean_import.py').read_text()
    database=next(ast.get_source_segment(source,n) for n in ast.parse(source).body
                  if isinstance(n,ast.ClassDef) and n.name=='Database')
    script=f"""import sys
from pathlib import Path
sys.path.insert(0,{str(R1)!r})
import entry
entry.load()
{_mock_code()}
from lawrag.pipeline import oracle_clean_import as clean
from semantic_runtime import oracle_dp_assets as assets
{database}
schema=SchemaOracle();schema.created=set(schema.columns)
source=AssetOracle();query=QueryOracle()
class Delegate:
 def request(self,method,path,json):
  if 'WHERE 1=0' in json['statementText']:
   return {{'items':[{{'resultSet':{{'items':[],'hasMore':False,'offset':0}}}}]}}
  text=json['statementText']
  target=schema if ':owner' in text and 'ALL_' in text else query if 'LEGAL_RAG_QUERY_' in text else source
  return target.request(method,path,json)
db=Database(Delegate())
try:clean.run(db,{str(work)!r},target_binding='fixture',action='plan')
except io.DPError as exc:assert str(exc)=='QUERY_RECORD_KEY: invalid lookup field',str(exc)
else:raise AssertionError('sealed R1 must reproduce the photographed error')
assert not any('DELETE FROM' in s or 'INSERT INTO' in s for s in db.statements)
"""
    runner=tmp_path/'r1_failure.py';runner.write_text(script)
    result=subprocess.run([sys.executable,str(runner)],text=True,capture_output=True)
    assert result.returncode==0,result.stdout[-2000:]+result.stderr[-4000:]
    return db,work


def test_actual_sealed_r1_failure_to_new_plan_load_and_repeat(failed_r1):
    db,work=failed_r1;logs=work/'oracle-clean-r1'
    before=json.loads((logs/'state.json').read_text())
    calls=(logs/'calls.jsonl').read_text()
    plan=clean.run(db,work,target_binding='fixture',recover_r1_plan=True)
    assert plan['status']=='CLEAN_PLAN_READY'
    now=json.loads((logs/'state.json').read_text())
    assert now['deadline']==before['deadline']
    assert json.loads((logs/'state.r1-key-failure.json').read_text())==before
    assert (logs/'calls.jsonl').read_text().startswith(calls)
    assert not any('DELETE FROM' in s or 'INSERT INTO' in s for s in db.statements)
    result=clean.run(db,work,target_binding='fixture',action='replace')
    assert result['status']=='CLEAN_LOAD_COUNTS_CONFIRMED'
    values=[r for r in db.rows[q.ROW] if r['KIND'].endswith('.overflow_sample')]
    assert len(values)==1 and json.loads(values[0]['VALUE_JSON'])['target']=='가'*171
    assert values[0]['TARGET_ID']==q.lookup_key('가'*171)
    assert clean.run(db,work,target_binding='fixture',action='resume')==result
    assert sum('DELETE FROM' in s for s in db.statements)==1


def test_delivered_r2_notebook_recovers_actual_r1_failure(failed_r1,tmp_path):
    from test_oracle_clean_import import exercise_packaged_notebook
    db,work=failed_r1
    before=(work/'oracle-clean-r1/state.json').read_bytes()
    exercise_packaged_notebook(failed_r1,tmp_path,'r2')
    old=json.loads(before)
    new=json.loads((work/'oracle-clean-r1/state.json').read_text())
    assert new['deadline']==old['deadline'] and new['status']=='COMPLETE'
    assert json.loads((work/'oracle-clean-r1/state.r1-key-failure.json').read_text())==old


@pytest.mark.parametrize('defect',['code','data','target','plan','write','deadline','pending','reset','no_opt_in'])
def test_failed_r1_adoption_rejects_unsafe_state(failed_r1,defect):
    db,work=failed_r1;logs=work/'oracle-clean-r1';path=logs/'state.json'
    state=json.loads(path.read_text())
    if defect=='code':state['identity']['code']='0'*64
    elif defect=='data':state['identity']['data']='0'*64
    elif defect=='target':state['identity']['target']='other'
    elif defect=='plan':io.atomic_json(logs/'plan.json',{})
    elif defect=='write':
        with (logs/'calls.jsonl').open('a') as f:
            f.write(io.canonical({'binding':io.digest(state['identity']),'status':'STARTED','write':True,'call':999})+'\n')
    elif defect=='deadline':state['deadline']=1
    elif defect=='pending':state['pending']={'unknown':True}
    elif defect=='reset':state['reset_complete']=True
    io.atomic_json(path,state);before=path.read_bytes()
    with pytest.raises(io.DPError):
        clean.run(db,work,target_binding='fixture',recover_r1_plan=defect!='no_opt_in')
    assert path.read_bytes()==before
    assert not db.statements
