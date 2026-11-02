import ast
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zipfile
from unittest.mock import patch

import pytest

HERE=Path(__file__).resolve().parent
CODE=HERE/'candidate'
sys.path[:0]=[str(CODE),str(CODE/'client'),str(CODE/'client/02_BACKEND')]
from lawrag.pipeline import oracle_query_publish as new, oracle_deferred_import as deferred

with zipfile.ZipFile(HERE.parent/'existing_nfs_deferred_verify_20261030_r6b/DATAIKU_EXISTING_NFS_CLIENT_20261030_R6B.zip') as z:
    OLD=z.read('client/02_BACKEND/lawrag/pipeline/oracle_query_publish.py').decode()
oldvars=dict(vars(new))
for node in ast.parse(OLD).body:
    if isinstance(node,ast.FunctionDef) and node.name in {'asset_rows','_asset_rows'}:
        exec(compile(ast.get_source_segment(OLD,node),'sealed-r6b','exec'),oldvars)


@pytest.mark.parametrize('kind',['unit','generic','words','empty','contentless'])
def test_all_rows_ids_positions_and_manifest_chains_match_r6b(tmp_path,kind):
    file=tmp_path/'units.sqlite'
    db=sqlite3.connect(file)
    if kind in {'unit','empty'}:
        db.execute('CREATE TABLE unit(key TEXT PRIMARY KEY,source_id TEXT,document_id TEXT,json TEXT)')
        db.execute('CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body,title,tokenize="unicode61")')
        if kind!='empty':
            for i in (7,2,40):
                key='D'*500+str(i)
                db.execute('INSERT INTO unit VALUES(?,?,?,?)',(key,'S'*500,'D'*500,'{}'))
                db.execute('INSERT INTO unit_fts(rowid,key,body,title) VALUES(?,?,?,?)',(i,key,'반복 반복 café 예외 A A', '제목 반복'))
    elif kind=='words':
        db.execute('CREATE TABLE label(source TEXT,node_id TEXT)')
        db.execute('CREATE VIRTUAL TABLE words USING fts5(value)')
        for i,value in enumerate(['aaa aaa bbb','ccc aaa',''],1):
            db.execute('INSERT INTO label(rowid,source,node_id) VALUES(?,?,?)',(i,'s',str(i)))
            db.execute('INSERT INTO words(rowid,value) VALUES(?,?)',(i,value))
    else:
        db.execute("CREATE VIRTUAL TABLE search USING fts5(body,title"+(",content=''" if kind=='contentless' else '')+")")
        for i in (20,3,1):db.execute('INSERT INTO search(rowid,body,title) VALUES(?,?,?)',(i,'a b a c 한글','a a'))
    db.commit();db.close()
    before=file.read_bytes()
    expected=list(oldvars['asset_rows'](file,'fulltext/units.sqlite'))
    got=list(new.asset_rows(file,'fulltext/units.sqlite'))
    assert got==expected
    chains={}
    for rows in (expected,got):
        state={}
        for row in rows:
            old=state.get(row['kind'],(0,'0'*64))
            state[row['kind']]=(old[0]+1,new.digest([old[1],row['row_id'],row['sha256']]))
        chains[id(rows)]=state
    assert chains[id(expected)]==chains[id(got)]
    assert file.read_bytes()==before


def test_sort_carries_four_fields_and_metadata_lookups_once_per_document(tmp_path):
    file=tmp_path/'fts.sqlite';db=sqlite3.connect(file)
    db.execute('CREATE VIRTUAL TABLE search USING fts5(body)')
    db.executemany('INSERT INTO search VALUES(?)',[('a a a b c',),('a b a a',)])
    db.commit();db.close()
    original=sqlite3.connect;statements=[]
    def connect(*a,**k):
        db=original(*a,**k);db.set_trace_callback(statements.append);return db
    with patch.object(new.sqlite3,'connect',side_effect=connect):list(new.asset_rows(file,'fts.sqlite'))
    sorts=[s for s in statements if s.startswith('SELECT doc,col,term,offset FROM')]
    assert len(sorts)==1 and 'JOIN' not in sorts[0]
    metadata=[s for s in statements if ' AS logical_id,' in s and 'WHERE f.rowid=' in s]
    assert len(metadata)==2


def prepared(tmp_path,source=None,files=None):
    return deferred.prepared_descriptor(tmp_path,source or {'id':'same'},files or {'x':'sha'},tmp_path)


def test_completed_descriptor_reused_and_incomplete_prepare_not_cached(tmp_path):
    result=({}, {'x':'sha'}, {'k':{'rows':3,'chain':'x'}})
    with patch.object(new,'describe',side_effect=[RuntimeError('interrupted'),result]) as describe:
        with pytest.raises(RuntimeError):prepared(tmp_path)
        assert not (tmp_path/'projection-descriptor-r7.json').exists()
        assert prepared(tmp_path)==result[1:]
        assert prepared(tmp_path)==result[1:]
        assert describe.call_count==2


@pytest.mark.parametrize('change',['source','files','code'])
def test_descriptor_binding_change_recomputes_preserves_old(tmp_path,change):
    result=({}, {'x':'sha'}, {})
    with patch.object(new,'describe',return_value=result) as describe:
        prepared(tmp_path)
        raw=(tmp_path/'projection-descriptor-r7.json').read_bytes()
        if change=='code':
            original=deferred.io.file_sha
            with patch.object(deferred.io,'file_sha',side_effect=lambda p:'new' if str(p)==new.__file__ else original(p)):
                prepared(tmp_path)
        else:prepared(tmp_path,source={'id':'new'} if change=='source' else None,files={'x':'new'} if change=='files' else None)
        assert describe.call_count==2
        archive=list(tmp_path.glob('projection-descriptor-r7-*.json'))
        assert len(archive)==1 and archive[0].read_bytes()==raw


def test_descriptor_corruption_rejected(tmp_path):
    with patch.object(new,'describe',return_value=({}, {}, {})):prepared(tmp_path)
    p=tmp_path/'projection-descriptor-r7.json';value=json.loads(p.read_text());value['tables']={'fake':{}}
    p.write_text(json.dumps(value))
    with pytest.raises(deferred.io.DPError,match='CHECKSUM'):prepared(tmp_path)


def test_pins_and_source_resume_modules_identical_to_r6b():
    for n,h in json.loads((CODE/'PACKAGE_FILES.json').read_text()).items():assert deferred.io.file_sha(CODE/n)==h
    for n,h in json.loads((CODE/'client/CODE_PINS.json').read_text())['files'].items():assert deferred.io.file_sha(CODE/'client'/n)==h
    with zipfile.ZipFile(HERE.parent/'existing_nfs_deferred_verify_20261030_r6b/DATAIKU_EXISTING_NFS_CLIENT_20261030_R6B.zip') as z:
        for name in ('oracle_migration.py','oracle_full_package.py'):
            relative='client/02_BACKEND/lawrag/pipeline/'+name
            assert z.read(relative)==(CODE/relative).read_bytes()


def test_old_query_plan_rejected_before_heavy_preparation(tmp_path):
    from lawrag.pipeline import oracle_full_package as full
    state={'deferred':{'plan':{'query_release_id':'old'}}}
    with patch.object(full,'immutable_inputs',side_effect=AssertionError('must stop first')):
        with pytest.raises(deferred.io.DPError,match='before R7 preparation'):
            deferred.execute(None,root=tmp_path,folder=tmp_path,info={},state=state,
                receipt=tmp_path/'state.json',logs=tmp_path,target_binding='DB',action='load_only',
                remaining=None,stage=None,sql=None,schema={})
