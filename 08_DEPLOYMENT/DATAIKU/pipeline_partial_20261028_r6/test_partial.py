import base64,copy,hashlib,io,json,sqlite3,sys,time,types,zipfile
from pathlib import Path
import pytest
from test_compute import env,Folder,identity,module,HERE


def coverage(partial=True):
    omitted=[{'document_id':'bad','source':'internal','name':'실패.pdf','selection':'SELECTED',
              'phases':{'structure':{'state':'FAILED','error':'synthetic parser failed'}}}] if partial else []
    return {'schema_version':'dataiku-partial-structure-v1','coverage':'PARTIAL' if partial else 'COMPLETE',
            'selected_document_ids':['good'],'selected_count':1,'omitted_count':len(omitted),
            'attempted_count':1+len(omitted),'original_structure_ok':not partial,'omitted_documents':omitted}


def result_bytes(e,tmp_path,*,partial=True,ids=('good',),value=None,meta=None):
    value=value or coverage(partial)
    import pipeline_coverage as pc
    root=tmp_path/'result-fixture';root.mkdir(exist_ok=True)
    db=root/'store.sqlite'
    if db.exists():db.unlink()
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE document(document_id TEXT PRIMARY KEY)')
        c.executemany('INSERT INTO document VALUES(?)',[(x,) for x in ids])
    e.t.write(root/'coverage.json',value)
    (root/'excluded.csv').write_text('document_id,error\n'+('bad,synthetic parser failed\n' if partial else ''))
    paths={'generation/store.sqlite':db,'audit/pipeline-coverage.json':root/'coverage.json','audit/excluded-documents.csv':root/'excluded.csv'}
    e.t.pack(paths,root/'result.zip',metadata={'code_sha256':e.c.EXPECTED,'coverage':meta or pc.summary(value)})
    return (root/'result.zip').read_bytes()


def receive(e,tmp_path,raw):
    store=e.c.ManagedJob(e.c.Scope(Folder()),'one',identity())
    state={'handle':'a'*32,'instance':'b'*32,'handle_token':'c'*64,'code_sha256':e.c.EXPECTED}
    class Wire:
        def call(self,op,**kw):
            offset=kw['offset'];block=raw[offset:offset+e.t.CHUNK]
            return {'content':base64.b64encode(block).decode(),'bytes':len(block),'offset':offset,'sha256':hashlib.sha256(block).hexdigest()}
    e.c.collect_result(store,Wire(),state,{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},tmp_path)
    return store


@pytest.mark.parametrize('partial',[False,True])
def test_publish_coverage_saved_and_complete_label_honest(env,tmp_path,partial):
    store=receive(env,tmp_path,result_bytes(env,tmp_path,partial=partial))
    record=env.c.structured_record(store)
    assert record['coverage']['omitted_count']==int(partial)
    assert env.c.structure_status(store)==('STRUCTURED_WITH_OMISSIONS' if partial else 'STRUCTURED')
    assert all(store.folder.get_download_stream(p).read() for p in record['coverage_paths'].values())
    restored=env.c.ManagedJob(store.folder,'one',identity())
    assert env.c.structured_record(restored)==record


@pytest.mark.parametrize('change',['count','overlap','zero','pending','label','metadata','hash','missing'])
def test_bad_coverage_never_published(env,tmp_path,change):
    value=coverage();meta=None
    if change=='count':value['selected_count']=2
    if change=='overlap':value['omitted_documents'][0]['document_id']='good'
    if change=='zero':value.update(selected_count=0,selected_document_ids=[],attempted_count=1)
    if change=='pending':value['omitted_documents'][0]['phases']['structure']['state']='PENDING'
    if change=='label':value['coverage']='COMPLETE'
    if change=='metadata':meta={'coverage':'COMPLETE'}
    raw=result_bytes(env,tmp_path,value=value,meta=meta)
    if change in {'hash','missing'}:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:entries={n:z.read(n) for n in z.namelist()}
        if change=='hash':entries['audit/pipeline-coverage.json']+=b' '
        else:del entries['audit/pipeline-coverage.json']
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            for n,v in entries.items():z.writestr(n,v)
        raw=b.getvalue()
    with pytest.raises((ValueError,KeyError)):receive(env,tmp_path,raw)


@pytest.mark.parametrize('mismatch',[False,True])
def test_load_checks_exact_documents_before_any_sql(env,tmp_path,monkeypatch,mismatch):
    raw=result_bytes(env,tmp_path,ids=('good','bad') if mismatch else ('good',))
    upstream=receive(env,tmp_path,raw);c=env.c
    c.r.put_json(upstream.folder,'jobs/one/structured.json',c.structured_record(upstream),tmp_path)
    folders={'landing':Folder(),'structured':upstream.folder.folder,'load':Folder()};calls=[]
    monkeypatch.setattr(c.r,'input_receipts',lambda _: {})
    monkeypatch.setattr(c,'context',lambda *a:(types.SimpleNamespace(SQL_PATH='fixture',schema_map=None),{'schema':'SIDDS'},None,identity()))
    def sql(client,returned,attempt,**kw):
        calls.append(1);attempt.mkdir()
        c.t.write(attempt/'receipt.json',{'ok':True})
        with sqlite3.connect(returned/'generation/store.sqlite') as db:
            assert db.execute('SELECT document_id FROM document').fetchall()==[('good',)]
        return {'source_release_id':'test','query':{'release_id':'query','rows':1}}
    monkeypatch.setattr(c.r.client,'load_oracle',sql)
    if mismatch:
        with pytest.raises(ValueError,match='GENERATION_COVERAGE'):c.load({},folders,{},tmp_path,'one')
        assert calls==[]
    else:
        answer=c.load({},folders,{},tmp_path,'one')
        assert len(calls)==1 and answer['status']=='COMPLETE_WITH_OMISSIONS'
        assert answer['coverage']['omitted_count']==1 and answer['genos_calls']==0


def actual_config(e):return module('actual_config',e.root/'parser_config.py')


def test_original_http_mode_does_not_require_pod_yaml(env,monkeypatch):
    monkeypatch.delenv('LEGAL_PIPELINE_PARSER_MODE',raising=False)
    monkeypatch.delenv('GENOS_STRUCTURE_CONFIG',raising=False)
    # Prior R4 variables can exist, but explicit selected full-flow mode owns transport.
    monkeypatch.setenv('GENOS_PREPROCESSOR_TRANSPORT','pod')
    p=actual_config(env);value=p.require(env.root)
    assert value['pipeline_parser_mode']=='existing-http' and value['ready']
    assert value['response_mode']=='auto'
    monkeypatch.setenv('GENOS_LLM_MODEL','changed')
    with pytest.raises(ValueError,match='CONFIG_CHANGED'):p.require(env.root,value['config_sha256'])


@pytest.mark.parametrize('mode',['typo','same-pod'])
def test_invalid_or_unconfigured_pod_mode_never_falls_back(env,monkeypatch,mode):
    monkeypatch.setenv('LEGAL_PIPELINE_PARSER_MODE',mode)
    monkeypatch.delenv('GENOS_STRUCTURE_CONFIG',raising=False)
    value=actual_config(env).inspect(env.root)
    assert not value['ready']


@pytest.mark.parametrize('returncode',[1,130,-9])
def test_process_failure_never_selects_successes(env,returncode):
    import partial_pipeline
    with pytest.raises(ValueError,match='PROCESS_FAILED'):partial_pipeline.select(env.tmp/'absent','run',returncode)


@pytest.mark.parametrize('previous',['r3','r4','r5'])
@pytest.mark.parametrize('case',['zero','nonzero','missing','tampered','count_mismatch','exhausted'])
def test_upgrade_preserves_review_proof_and_limits(env,tmp_path,previous,case):
    old=HERE.parent/'pipeline_pod_20261028_r4/test_pod.py'
    test=module('review_tests',old)
    test.OLD={'r3':'8be91b1939678d31f7e881417091d6a46b9e706704b316044f5ccb6af2752ee1',
              'r4':'8789724175dbe2177eb52c535a6e6b2279af7a4687d7fb0ec24c28a241e52685',
              'r5':'78811f3b4620c91057a995eaf567cf078c886c6090d3ea02061f3bef2ec5901c'}[previous]
    test.test_r3_migration_budget_proof(env,tmp_path,case)


def failed_structure(e):
    from lawrag.pipeline import genos_build,genos_stages,genos_status
    workspace=e.tmp/'workspace';data=workspace/'01_DATA';raw=data/'RAW/internal';raw.mkdir(parents=True)
    xml='<법령><기본정보><법령명_한글>모의규정</법령명_한글></기본정보><조문><조문단위><조문번호>1</조문번호><조문제목>정의</조문제목><조문내용>“영업일”이란 은행이 영업하는 날을 말한다.</조문내용></조문단위></조문></법령>'
    (raw/'good.xml').write_text(xml);(raw/'bad.xml').write_text(xml.replace('모의규정','실패규정'))
    plan=genos_build.inventory(raw,'internal',None);(raw/'bad.xml').unlink()
    options=genos_build.parser().parse_args(['build','--input-root',str(raw),'--build-dir',str(data/'work'),'--execute'])
    logs=data/'LOGS/failed';ledger=genos_status.Ledger(logs)
    progress=types.SimpleNamespace(**{n:lambda *a,**k:None for n in ('document','emit','finish','error')})
    try:
        ledger.start(plan['files'],'structure')
        result=genos_stages.execute(plan,options,data,'failed','structure',dependencies={'fixture':'xml'},progress=progress,status=ledger)
        assert result['passed']==1 and not result['ok']
        ledger.finish('FAILED')
    finally:ledger.close()
    e.t.write(logs/'result-20261028.json',{**result,'stage':'structure','source_errors':[]})
    return workspace,logs


def test_partial_selection_reuses_verified_success_preserves_failed_parent(env):
    import partial_pipeline as p
    workspace,logs=failed_structure(env)
    before={f:f.read_bytes() for f in logs.iterdir() if f.is_file()}
    value=p.select(workspace,'failed',2)
    assert value['selected_count']==value['omitted_count']==1 and not value['original_structure_ok']
    assert p.select(workspace,'failed',2)==value
    assert all(f.read_bytes()==b for f,b in before.items())
    assert (workspace.parent/'excluded-documents.csv').is_file()


@pytest.mark.parametrize('change',['run_error','running','source_error','result_missing','receipt_changed','integrity_failure','exit_mismatch'])
def test_invalid_structure_is_not_masked_by_partial_selection(env,change):
    from lawrag.pipeline import genos_status
    import partial_pipeline as p
    workspace,logs=failed_structure(env);rc=2
    if change in {'run_error','running','integrity_failure'}:
        with sqlite3.connect(logs/genos_status.DATABASE) as db:
            if change=='run_error':db.execute("UPDATE attempts SET error='repository manifest mismatch'")
            elif change=='running':db.execute("UPDATE attempts SET status='RUNNING'")
            else:
                for did,raw in db.execute('SELECT id,data FROM documents').fetchall():
                    row=json.loads(raw)
                    if row['phases']['structure']['state']=='FAILED':
                        row['phases']['structure']['error']='source hash mismatch'
                        db.execute('UPDATE documents SET data=? WHERE id=?',(json.dumps(row),did))
    if change=='source_error':
        f=logs/'result-20261028.json';env.t.write(f,{**env.t.read(f),'source_errors':['input inventory failed']})
    if change=='result_missing':(logs/'result-20261028.json').unlink()
    if change=='receipt_changed':
        f=logs/'structure-selection.json';v=env.t.read(f);next(iter(v['documents'].values()))['receipt_sha256']='0'*64;env.t.write(f,v)
    if change=='exit_mismatch':rc=0
    with pytest.raises(ValueError):p.select(workspace,'failed',rc)
    assert not (workspace.parent/'pipeline-coverage.json').exists()
