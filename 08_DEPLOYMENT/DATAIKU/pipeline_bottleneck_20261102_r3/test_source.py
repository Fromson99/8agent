import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import types
import pytest

HERE=Path(__file__).parent
sys.path.insert(0,str(HERE/'package'))
import g19diag_source as source
import g19diag_oracle_worker as worker
import g19diag_notebook as notebook
BASE=HERE.parent/'gold_fresh_1_20261102_r1/package'
spec=importlib.util.spec_from_file_location('g19_source_test_loader',BASE/'run.py')
loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
from lawrag.pipeline import oracle_query_publish as pub
from semantic_runtime.oracle_dp_io import COLUMNS
import jdbc_transport


def context(root,asset,table):
    kind=pub._kind(asset,table)
    return {'root':str(root),'state':{'binding':{'files':{asset:'prepared-file-hash','manifest.json':'a'*64},'query_release':'b'*64}},
            'descriptor':{'tables':{kind:{'asset':asset,'table':table,'rows':2000}}}},kind


@pytest.mark.parametrize('table',['entry_corpus_link','occurrence','occurrence_keys'])
def test_original_distinct_table_and_view_match_installed_projection(tmp_path,table):
    asset='sample.sqlite';path=tmp_path/asset
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE base(id TEXT PRIMARY KEY,document_id TEXT,text TEXT)')
        db.executemany('INSERT INTO base VALUES(?,?,?)',[(str(i),'D','secret '+str(i)) for i in range(2050)])
        db.execute('CREATE VIEW '+table+' AS SELECT * FROM base')
    before=path.read_bytes();ctx,kind=context(tmp_path,asset,table)
    rows,meta=source.sample(ctx,loader,'SRCH_ROW',kind)
    assert meta['status']=='OK' and len(rows)==2000
    expected=[loader.query_row('b'*64,r) for r in pub.asset_rows(path,asset) if r['kind']==kind][:2000]
    assert rows==expected and len({r['RFRN_DTA_ID'] for r in rows})==2000
    assert 'secret' not in json.dumps(meta) and path.read_bytes()==before


@pytest.mark.parametrize('fts',['words','unit_fts'])
def test_complete_fts_groups_match_installed_projection_without_source_writes(tmp_path,fts):
    path=tmp_path/'fts.sqlite'
    with sqlite3.connect(path) as db:
        if fts=='words':
            db.execute('CREATE VIRTUAL TABLE words USING fts5(body)')
            db.executemany('INSERT INTO words VALUES(?)',[('alpha alpha beta',),('beta gamma',),('zulu',)])
        else:
            db.execute('CREATE TABLE unit(key TEXT,document_id TEXT,source_id TEXT)')
            db.execute('CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,body)')
            db.executemany('INSERT INTO unit VALUES(?,?,?)',[('u1','d1','s1'),('u2','d2','s2')])
            db.executemany('INSERT INTO unit_fts VALUES(?,?)',[('u1','alpha alpha beta'),('u2','beta gamma')])
    before=path.read_bytes();ctx,kind=context(tmp_path,'fts.sqlite',fts+'_posting')
    rows,meta=source.sample(ctx,loader,'SRCH_ROW',kind)
    assert meta['status']=='OK'
    expected=[loader.query_row('b'*64,r) for r in pub.asset_rows(path,'fts.sqlite') if r['kind']==kind]
    assert sorted(rows,key=lambda r:r['RFRN_DTA_ID'])==sorted(expected,key=lambda r:r['RFRN_DTA_ID'])
    assert path.read_bytes()==before


def test_oversize_fts_term_is_skipped_not_truncated(tmp_path):
    path=tmp_path/'fts.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE VIRTUAL TABLE words USING fts5(body)')
        db.execute('INSERT INTO words VALUES(?)',(' '.join(['alpha']*4200+['beta']),))
    ctx,kind=context(tmp_path,'fts.sqlite','words_posting')
    rows,meta=source.sample(ctx,loader,'SRCH_ROW',kind)
    assert len(rows)==1 and meta['oversize_terms_skipped']==1
    value=json.loads(rows[0]['SRCH_DATA_CTNT'])
    assert value['token']=='beta' and value['positions']==[4200]


@pytest.mark.parametrize('source_kind,key',[('document','DOC_VER'),('source_unit','DOC_UNIT'),('block_payload','DOC_BLK')])
def test_original_document_mapping_and_no_repeated_bodies(tmp_path,source_kind,key):
    columns=[('json' if c=='SOURCE_JSON' else c.lower()) for c in COLUMNS[source_kind] if c!='DATASET_VERSION']
    path=tmp_path/'store.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE '+source_kind+'('+','.join(c+(' INTEGER' if c=='json_text_elided' else ' TEXT') for c in columns)+')')
        for i in range(105):
            values=[(0 if c=='json_text_elided' else json.dumps({'n':i}) if c=='json' else str(i) if c in ('document_id','unit_id','block_id') else 'source') for c in columns]
            db.execute('INSERT INTO '+source_kind+' VALUES('+','.join('?' for _ in columns)+')',values)
    ctx,_=context(tmp_path,'store.sqlite',source_kind);before=path.read_bytes()
    rows,meta=source.sample(ctx,loader,key)
    assert meta['status']=='OK' and len(rows)==105
    assert len({r['DOC_ID'] for r in rows})==105 and path.read_bytes()==before


def test_unbound_file_active_journal_and_deadline_never_insert_partial(tmp_path):
    path=tmp_path/'sample.sqlite'
    with sqlite3.connect(path) as db: db.execute('CREATE TABLE item(id TEXT)');db.execute("INSERT INTO item VALUES('x')")
    ctx,kind=context(tmp_path,'sample.sqlite','item')
    ctx['state']['binding']['files'].pop('sample.sqlite')
    rows,m=source.sample(ctx,loader,'SRCH_ROW',kind)
    assert not rows and m['status']=='SOURCE_SAMPLE_UNMEASURED'
    ctx['state']['binding']['files']['sample.sqlite']='h'
    journal=Path(str(path)+'-journal');journal.write_text('active')
    rows,m=source.sample(ctx,loader,'SRCH_ROW',kind)
    assert not rows and m['status']=='SOURCE_SAMPLE_UNMEASURED'
    journal.unlink()
    rows,m=source.sample(ctx,loader,'SRCH_ROW',kind,seconds=0)
    assert not rows


def test_source_change_discards_rows(tmp_path,monkeypatch):
    path=tmp_path/'sample.sqlite'
    with sqlite3.connect(path) as db: db.execute('CREATE TABLE item(id TEXT)');db.execute("INSERT INTO item VALUES('x')")
    ctx,kind=context(tmp_path,'sample.sqlite','item')
    original=source.ordinary
    def changing(*args):
        yield from original(*args)
        with sqlite3.connect(path) as db: db.execute("INSERT INTO item VALUES('y')")
    monkeypatch.setattr(source,'ordinary',changing)
    rows,m=source.sample(ctx,loader,'SRCH_ROW',kind)
    assert not rows and m['status']=='SOURCE_SAMPLE_UNMEASURED'


def test_real_jdbc_wrapper_times_before_decode_and_receipt_fields():
    c=loader.Contract(BASE/'contract.json')
    record=pub.record('asset_fixture.item',{'body':'가'*20000},key='fixture')
    row=loader.query_row('b'*64,record)
    sql,binds=c.batch('SRCH_ROW',[row]);nonce='a'*32
    rendered=worker.instrument_payload_clock(jdbc_transport.render(worker.rollback_probe_sql(sql,nonce,payload_clock=True),binds,write=True))
    assert rendered.index('g19_transport_t0:=') < rendered.index('UTL_COMPRESS.LZ_UNCOMPRESS') < rendered.index('d0:=DBMS_UTILITY.GET_TIME')
    assert 'COMMIT;' not in rendered and 'DBMS_LOB.COMPARE' in rendered
    assert "||' p='||TO_CHAR(MOD(d0-g19_transport_t0" in rendered
    times=worker.marker_times(Exception('ORA-20084: G19_PROBE_OK_'+nonce+' i=24 v=24 r=1 p=200'),nonce)
    assert times['payload_db_seconds']==2 and times['insert_db_seconds']==.24
    with pytest.raises(ValueError):worker.instrument_payload_clock('BEGIN NULL; END;')


def test_result_pages_keep_all_three_batches_and_partial_status(monkeypatch):
    monkeypatch.setattr(notebook,'display_html',lambda x:None)
    r={'oracle':{'insert_probes':[{'table':'SRCH_ROW','kind':'asset_x.item','requested_rows':n,'rows':n,'request_seconds':n/1000,'status':'ROLLED_BACK_VERIFIED'} for n in (100,500,2000)]}}
    value=notebook.show('배치',r)
    assert '0.100' in value and '0.500' in value and '2.000' in value
    r['oracle']['insert_probes'].append({'table':'SRCH_ROW','kind':'asset_x.missing','status':'SOURCE_SAMPLE_UNMEASURED'})
    assert 'SOURCE_SAMPLE_UNMEASURED' in notebook.show('배치',r)
    assert '순수 네트워크가 아닙니다' in notebook.show('삽입',r)
