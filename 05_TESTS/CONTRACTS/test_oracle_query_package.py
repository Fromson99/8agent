"""Transport roundtrip, retained budgets, immutable Oracle imports and exact CLI."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest
from test_compact_v2_rag import structured_generation
from test_oracle_dp_runtime import published
from test_oracle_query_handoff_20261020 import handoff
from lawrag.pipeline import oracle_query_package as pack, oracle_query_publish as pub
from lawrag.pipeline.oracle_query_dataiku import render,DataikuClient
from semantic_runtime import oracle_dp_io as io,oracle_query_catalog as q

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_query_parts_20261020_r2/package'

@pytest.fixture
def package(handoff,tmp_path):
    module,ns,remote,schema,source,publication,generation=handoff
    folder=tmp_path/'out'
    result=pack.export(generation,folder,chunk_bytes=4000)
    client=ns['desk'].require_connection().client
    return folder,client,remote,source,publication,generation,ns


def call(p,tmp_path,action='publish',seconds=3600):
    return pack.import_db(p[1],p[0]/pack.DB_NAME,target_binding='mock-target',directory=tmp_path/'import',action=action,seconds=seconds)


def test_transport_matches_existing_publisher_and_roundtrips(package,tmp_path):
    folder,client,remote,source,original,generation,ns=package
    writes=source.writes
    meta=pack.verify_db(folder/pack.DB_NAME)
    assert io.digest(meta['source_release'])==original['release_id']
    old=pub.publish(client,generation=generation,source_release_id=original['release_id'],target_binding='mock-target',directory=tmp_path/'old')
    assert old['release_id']==io.digest(meta['query_manifest'])
    restored=pack.restore(folder/'download',tmp_path/'restored')
    assert io.file_sha(restored)==io.file_sha(folder/pack.DB_NAME)
    assert call(package,tmp_path,'check')['status']=='READY_TO_IMPORT'
    assert call(package,tmp_path)['release_id']==old['release_id']
    assert call(package,tmp_path,'status')['status']=='QUERY_PUBLICATION_VERIFIED'
    assert not remote.active and not remote.states and source.writes==writes
    deadline=json.loads((tmp_path/'import/state.json').read_text())['deadline']
    call(package,tmp_path)
    assert json.loads((tmp_path/'import/state.json').read_text())['deadline']==deadline


def test_export_resume_and_cli_uses_same_bundled_code(package,tmp_path):
    folder,_,_,_,_,generation,_=package
    before=io.file_sha(folder/pack.DB_NAME)
    pack.export(generation,folder,chunk_bytes=4000)
    assert io.file_sha(folder/pack.DB_NAME)==before
    out=tmp_path/'cli'
    cmd=['bash',str(DELIVERY/'CODESPACE_QUERY_50MB_RUN.txt'),'export','--generation',str(generation),'--output',str(out)]
    process=subprocess.run(cmd,cwd=tmp_path,text=True,capture_output=True,env={**os.environ,"PATH":str(ROOT/".venv/bin")+":"+os.environ["PATH"]})
    assert process.returncode==0,process.stdout+process.stderr
    bundled=pack.verify_db(out/pack.DB_NAME)['query_manifest']
    working=pack.verify_db(folder/pack.DB_NAME)['query_manifest']
    # The sealed historical package keeps its own publisher fingerprint.
    # Its data projection must match; its code hash must match its actual code.
    assert bundled['publisher_sha256']==io.file_sha(DELIVERY/'runtime/lawrag/pipeline/oracle_query_publish.py')
    assert working['publisher_sha256']==io.file_sha(pub.__file__)
    # New auxiliary-key metadata is explicit; this short-key fixture's rows,
    # chains and all other schema/source bindings must remain byte-identical.
    current=json.loads(json.dumps(working))
    for spec in current['tables'].values():
        if 'columns' in spec:
            assert spec.pop('lookup_encoding')==q.LOOKUP_ENCODING
    assert {k:v for k,v in bundled.items() if k!='publisher_sha256'}=={
        k:v for k,v in current.items() if k!='publisher_sha256'}
    with sqlite3.connect(out/pack.DB_NAME) as historical, sqlite3.connect(folder/pack.DB_NAME) as latest:
        assert historical.execute('SELECT seq,body FROM query_row ORDER BY seq').fetchall()==latest.execute(
            'SELECT seq,body FROM query_row ORDER BY seq').fetchall()


@pytest.mark.parametrize('mode',['missing','append','path','duplicate'])
def test_missing_damaged_and_traversal_parts_rejected(package,tmp_path,mode):
    parts=package[0]/'download';m=parts/'parts-manifest.json';v=json.loads(m.read_text());name=v['parts'][0]['name']
    if mode=='missing':(parts/name).rename(parts/'saved-part')
    if mode=='append':
        with (parts/name).open('ab') as f:f.write(b'X')
    if mode=='path':v['parts'][0]['name']='../escape';m.write_text(json.dumps(v))
    if mode=='duplicate':v['parts'].append(v['parts'][0]);m.write_text(json.dumps(v))
    with pytest.raises(io.DPError,match='PART_'):pack.restore(parts,tmp_path/'bad')
    assert not (tmp_path/'bad'/pack.DB_NAME).exists()


def test_db_tamper_rejected_before_any_sql(package,tmp_path):
    with sqlite3.connect(package[0]/pack.DB_NAME) as db:db.execute("UPDATE query_row SET body='{}' WHERE seq=1")
    before=len(package[2].calls)
    with pytest.raises(io.DPError,match='ROW_SHAPE'):call(package,tmp_path)
    assert len(package[2].calls)==before


def test_loss_of_write_ack_resumes_and_keeps_deadline(package,tmp_path):
    package[2].fail_after_write=True
    with pytest.raises(io.DPError,match='WRITE_UNCONFIRMED'):call(package,tmp_path)
    state=json.loads((tmp_path/'import/state.json').read_text())
    assert state['status']=='FAILED' and package[2].rows and not package[2].releases
    assert call(package,tmp_path)['status']=='COMPLETE'
    assert json.loads((tmp_path/'import/state.json').read_text())['deadline']==state['deadline']
    assert not package[2].active


def test_missing_source_schema_and_expired_budget(package,tmp_path):
    source=package[3];rid=package[4]['release_id'];value=source.releases.pop(rid)
    with pytest.raises(io.DPError,match='RELEASE_MISSING'):call(package,tmp_path)
    assert not package[2].rows
    source.releases[rid]=value
    statepath=tmp_path/'import/state.json';state=json.loads(statepath.read_text());state['deadline']=1;statepath.write_text(json.dumps(state))
    with pytest.raises(io.BudgetPause):call(package,tmp_path)
    assert not package[2].rows and json.loads(statepath.read_text())['deadline']==1


def test_changed_target_remote_values_and_extra_kind(package,tmp_path):
    call(package,tmp_path)
    with pytest.raises(io.DPError,match='IMPORT_BINDING'):
        pack.import_db(package[1],package[0]/pack.DB_NAME,target_binding='other',directory=tmp_path/'import')
    key=next(iter(package[2].rows));old=package[2].rows[key];package[2].rows[key]={**old,'VALUE':'{}','N':2}
    with pytest.raises(io.DPError,match='QUERY_READBACK'):call(package,tmp_path,'status')
    package[2].rows[key]=old
    # Repeat publish revalidates every batch; a previously COMPLETE receipt is not trusted.
    call(package,tmp_path)
    key2=(key[0],'undeclared','0'*64);package[2].rows[key2]={**old,'KIND':'undeclared','ROW_ID':'0'*64}
    with pytest.raises(io.DPError,match='QUERY_TOTAL_COUNT'):call(package,tmp_path,'status')


def test_jdbc_renderer_escapes_literals_and_lob_boundaries():
    text="BEGIN INSERT INTO t(a,b) VALUES(:a,:body); -- :ignore\n COMMIT; END;"
    compiled=render(text,[('a',"x'); DROP TABLE t; --",'VARCHAR2'),('body',"한글😀'"*2000,'CLOB')],write=True)
    assert "'x''); DROP TABLE t; --'" in compiled
    assert 'DBMS_LOB.APPEND' in compiled and ':body' not in compiled
    assert '-- :ignore' in compiled
    with pytest.raises(io.DPError):render('SELECT :missing FROM DUAL',[])
    with pytest.raises(io.DPError):render('SELECT :n FROM DUAL',[('n',1.1,'NUMBER')])


def test_dataiku_bridge_cleans_nan_and_never_exposes_jdbc_details():
    import pandas as pd
    class Executor:
        def query_to_df(self,text,**kw):
            if kw.get('pre_queries'):return pd.DataFrame([{'OK':1}])
            assert kw == {'infer_from_schema':True,'parse_dates':False}
            return pd.DataFrame([{'N':3,'X':None}])
    client=DataikuClient(Executor(),'connection','project')
    result=client.request('POST',client.SQL_PATH,{'statementText':'SELECT :n AS N FROM DUAL','binds':[{'name':'n','value':3,'data_type':'NUMBER'}],'limit':1})
    assert result['items'][0]['resultSet']['items']==[{'N':3,'X':None}]
    class Broken:
        def query_to_df(self,*args,**kw):raise RuntimeError('password=secret; body=private ORA-01031')
    client.executor=Broken()
    with pytest.raises(io.DPError,match='ORA-01031') as error:client.request('POST',client.SQL_PATH,{'statementText':'SELECT 1 FROM DUAL','limit':1})
    assert 'secret' not in str(error.value) and 'private' not in str(error.value)


def test_export_interruption_resumes_committed_assets(handoff,tmp_path,monkeypatch):
    generation=handoff[6];folder=tmp_path/'interrupted';original=pub.projected_rows
    def fail(path,relative,source):
        if relative!='store.sqlite':raise io.DPError('INJECTED_STOP')
        yield from original(path,relative,source)
    monkeypatch.setattr(pub,'projected_rows',fail)
    with pytest.raises(io.DPError,match='INJECTED_STOP'):pack.export(generation,folder)
    assert (folder/(pack.DB_NAME+'.partial')).exists() and not (folder/pack.DB_NAME).exists()
    first=json.loads((folder/'export-state.json').read_text())
    monkeypatch.setattr(pub,'projected_rows',original)
    pack.export(generation,folder)
    assert pack.verify_db(folder/pack.DB_NAME)
    assert first['deadline']==json.loads((folder/'export-state.json').read_text())['deadline']
    assert 'FAILED' in (folder/'events.jsonl').read_text()


def test_export_lock_and_low_resource_guard(handoff,tmp_path,monkeypatch):
    folder=tmp_path/'lock'
    with pack.job(folder):
        with pytest.raises(io.DPError,match='IN_PROGRESS'):pack.export(handoff[6],folder)
    monkeypatch.setattr(pack.shutil,'disk_usage',lambda p:SimpleNamespace(free=1))
    with pytest.raises(io.BudgetPause,match='DISK_LOW'):pack.export(handoff[6],folder)
    assert not (folder/pack.DB_NAME).exists()


def test_actual_notebook_txt_managed_folder_restore(package,tmp_path):
    upload=tmp_path/'managed-folder';upload.mkdir()
    import shutil
    shutil.copyfile(DELIVERY.parent/'LEGAL_ORACLE_QUERY_PARTS_20261020_R2.zip',upload/'LEGAL_ORACLE_QUERY_PARTS_20261020_R2.zip')
    for p in (package[0]/'download').iterdir():shutil.copyfile(p,upload/p.name)
    source=(DELIVERY/'DATAIKU_QUERY_IMPORT_RUN.txt').read_text()
    source=source.replace('FOLDER_ID = "여기에_Managed_Folder_ID"','FOLDER_ID = "synthetic-folder"')
    shim='''import sys,types\nfrom pathlib import Path\nm=types.ModuleType("dataiku")\nclass Folder:\n    def __init__(self,ident): assert ident=="synthetic-folder"\n    def get_download_stream(self,name):return (Path(%r)/name.lstrip("/")).open("rb")\nm.Folder=Folder\nsys.modules["dataiku"]=m\n''' % str(upload)
    run=tmp_path/'run-notebook.py';run.write_text(shim+source)
    proc=subprocess.run([sys.executable,str(run)],cwd=tmp_path,text=True,capture_output=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    restored=tmp_path/'legal-query-transfer-r2-work/restored'/pack.DB_NAME
    assert io.file_sha(restored)==io.file_sha(package[0]/pack.DB_NAME)
    assert 'RESTORED_AND_VERIFIED' in proc.stdout


def test_unexpected_db_tables_and_descriptor_tamper_rejected(package):
    path=package[0]/pack.DB_NAME
    with sqlite3.connect(path) as db:db.execute('CREATE TABLE unexpected(secret TEXT)')
    with pytest.raises(io.DPError,match='DB_OBJECTS'):pack.verify_db(path)
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE unexpected')
        row=db.execute("SELECT body FROM metadata WHERE key='source_release'").fetchone()
        source=json.loads(row[0]);source['source_manifest_text']+=' '
        db.execute("UPDATE metadata SET body=? WHERE key='source_release'",(json.dumps(source),))
    with pytest.raises(io.DPError,match='SOURCE_DESCRIPTOR'):pack.verify_db(path)
