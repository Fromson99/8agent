"""Reproducible FTS nested-scan defect; logical output and R1 resume contracts."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_dp_runtime import published
from test_oracle_query_handoff_20261020 import handoff
from lawrag.pipeline import oracle_query_package as pack, oracle_query_publish as pub
from lawrag.pipeline import oracle_transfer_progress as progress
from semantic_runtime import oracle_dp_io as io

ROOT=Path(__file__).resolve().parents[2]
R1=ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_query_parts_20261020_r1/package'
R2=ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_query_parts_20261020_r2/package'


def legacy():
    spec=importlib.util.spec_from_file_location('lawrag.pipeline.legacy_query_publish',R1/'runtime/lawrag/pipeline/oracle_query_publish.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@pytest.mark.parametrize('detail',['full','column','none'])
def test_fts_rows_equal_legacy_with_empty_unicode_multicolumn_and_negative_ids(tmp_path,detail):
    path=tmp_path/'fts.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE VIRTUAL TABLE words USING fts5(text,more,detail='+detail+')')
        db.executemany('INSERT INTO words(rowid,text,more) VALUES(?,?,?)',[
            (-3,'alpha alpha beta','한글 😀 alpha'),(1,'',''),(7,None,'beta alpha'),(21,'한글 alpha','beta beta')])
    before=io.file_sha(path)
    old=list(legacy().asset_rows(path,'glossary/fts.sqlite'))
    actual=list(pub.asset_rows(path,'glossary/fts.sqlite'))
    assert actual==old and io.file_sha(path)==before


def test_unit_fts_owner_and_full_fixture_projection_equal(handoff):
    _,_,_,_,_,publication,generation=handoff
    root,manifest,items,_,selected=pack.immutable_inputs(generation)
    source=pack.offline_source(root,manifest,items,selected)
    old=legacy()
    for path in ['store.sqlite',*[a['path'] for a in items if a['path'].endswith('.sqlite')]]:
        assert list(old.projected_rows(root/path,path,source))==list(pub.projected_rows(root/path,path,source))


def test_lengths_use_pk_lookup_and_bounded_sqlite_work(tmp_path):
    path=tmp_path/'large.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE VIRTUAL TABLE words USING fts5(text)')
        db.executemany('INSERT INTO words VALUES(?)',[('alpha beta gamma delta',)]*1500)
    logs=[]
    with progress.tracking(tmp_path,lambda status,**fields:logs.append((status,fields))) as monitor:
        rows=list(pub.asset_rows(path,'large.sqlite'))
        assert monitor.fields['sqlite_steps']<5_000_000
    assert sum(r['value']['length'] for r in rows if r['kind'].endswith('_length'))==6000
    assert any(x[1].get('phase')=='FTS_LENGTH_AGGREGATE' for x in logs)
    db=sqlite3.connect(path);db.execute('CREATE TEMP TABLE query_export_lengths(doc INTEGER PRIMARY KEY,n INTEGER)')
    plan=list(db.execute('EXPLAIN QUERY PLAN SELECT f.rowid,v.n FROM words f LEFT JOIN temp.query_export_lengths v ON v.doc=f.rowid'))
    db.close()
    assert any('SEARCH v USING INTEGER PRIMARY KEY' in r[3] for r in plan)


def test_sqlite_callback_stops_on_budget_and_logs_work(tmp_path):
    db=sqlite3.connect(':memory:');logs=[]
    with progress.tracking(tmp_path,lambda status,**fields:logs.append((status,fields)),interval=.01) as monitor:
        monitor.deadline=time.time()-1
        with pytest.raises(io.BudgetPause,match='EXPORT_BUDGET'):
            with progress.sqlite_work(db):
                db.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000) SELECT SUM(x) FROM n').fetchone()
        assert monitor.fields['sqlite_steps']>0
    db.close()


@pytest.fixture
def r1_partial(structured_generation,tmp_path):
    output=tmp_path/'r1-output'
    code='''import sys
from pathlib import Path
sys.path.insert(0,%r)
import entry
p=entry.load()
original=p.pub.projected_rows
def interrupted(path,relative,source):
    if relative!='store.sqlite':raise p.io.DPError('INTENTIONAL_STOP')
    yield from original(path,relative,source)
p.pub.projected_rows=interrupted
try:p.export(%r,%r)
except p.io.DPError as exc:
    if 'INTENTIONAL_STOP' not in str(exc):raise
else:raise RuntimeError('fixture must stop')
''' % (str(R1),str(structured_generation),str(output))
    runner=tmp_path/'create-r1-partial.py';runner.write_text(code)
    result=subprocess.run([sys.executable,str(runner)],text=True,capture_output=True)
    assert result.returncode==0,result.stdout+result.stderr
    return output,structured_generation


def test_real_r1_partial_upgrades_with_same_prefix_deadline_and_import(r1_partial,handoff,tmp_path):
    output,generation=r1_partial
    prior=pack.bounded_json(output/'export-state.json')
    with sqlite3.connect(output/(pack.DB_NAME+'.partial')) as db:
        before=db.execute('SELECT * FROM query_row ORDER BY seq').fetchall()
    assert before
    run=subprocess.run(['bash',str(R2/'CODESPACE_QUERY_50MB_RUN.txt'),'export','--generation',str(generation),
        '--output',str(output),'--resume-r1'],cwd=tmp_path,text=True,capture_output=True,
        env={**os.environ,'PATH':str(ROOT/'.venv/bin')+':'+os.environ['PATH']})
    assert run.returncode==0,run.stdout+run.stderr
    result=pack.bounded_json(output/'export-state.json')
    now=pack.bounded_json(output/'export-state.json')
    assert now['deadline']==prior['deadline'] and pack.bounded_json(output/'export-state.r1-preserved.json')==prior
    with sqlite3.connect(output/pack.DB_NAME) as db:
        assert db.execute('SELECT * FROM query_row ORDER BY seq LIMIT ?',(len(before),)).fetchall()==before
    assert not (output/'query-data.zip').exists()
    restored=pack.restore(output/'download',tmp_path/'restored')
    assert io.file_sha(restored)==io.file_sha(output/pack.DB_NAME)
    meta=pack.verify_db(restored)
    # This fixture has the exact same source generation; use its existing synthetic Oracle source.
    client=handoff[1]['desk'].require_connection().client
    assert pack.import_db(client,restored,target_binding='mock-target',directory=tmp_path/'oracle',action='publish')['status']=='COMPLETE'
    assert result['query_release_id']==io.digest(meta['query_manifest'])
    assert 'ROWS_CHECKED' in (output/'events.jsonl').read_text()


@pytest.mark.parametrize('change',['unknown_code','source','row','deadline'])
def test_r1_invalid_upgrade_is_not_a_hash_bypass(r1_partial,change):
    output,generation=r1_partial;state=pack.bounded_json(output/'export-state.json')
    if change=='unknown_code':state['identity']['publisher_code']='0'*64
    elif change=='source':state['identity']['selection']='0'*64
    elif change=='deadline':state['deadline']=1
    else:
        with sqlite3.connect(output/(pack.DB_NAME+'.partial')) as db:db.execute("UPDATE query_row SET body='{}' WHERE seq=1")
    io.atomic_json(output/'export-state.json',state)
    with pytest.raises(io.DPError):pack.export(generation,output,resume_r1=True,direct_parts=True)
    assert not (output/pack.DB_NAME).exists()


def test_direct_parts_repeat_and_interruption_resume(handoff,tmp_path,monkeypatch):
    generation=handoff[6];output=tmp_path/'out'
    pack.export(generation,output)
    # Independent direct compression directory, same completed transport DB.
    folder=tmp_path/'stream';folder.mkdir();original=pack._PartsWriter._finish;failed=[False]
    def finish(self):
        original(self)
        if self.entries and not failed[0]:failed[0]=True;raise io.DPError('INJECTED_PART_STOP')
    monkeypatch.setattr(pack._PartsWriter,'_finish',finish)
    with pytest.raises(io.DPError,match='INJECTED'):pack.split_db_direct(output/pack.DB_NAME,folder,chunk_bytes=4000)
    assert not (folder/'download/parts-manifest.json').exists()
    monkeypatch.setattr(pack._PartsWriter,'_finish',original)
    first=pack.split_db_direct(output/pack.DB_NAME,folder,chunk_bytes=4000)
    manifest=(folder/'download/parts-manifest.json').read_bytes()
    assert pack.split_db_direct(output/pack.DB_NAME,folder,chunk_bytes=4000)==first
    assert (folder/'download/parts-manifest.json').read_bytes()==manifest
    restored=pack.restore(folder/'download',tmp_path/'restored')
    assert io.file_sha(restored)==io.file_sha(output/pack.DB_NAME)
