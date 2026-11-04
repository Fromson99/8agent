import copy
import fcntl
import hashlib
import importlib.util
import json
import os
import io
from pathlib import Path
import sqlite3
import sys
import subprocess
import tempfile
import signal
import time
import shutil
from types import SimpleNamespace as NS
import pytest

HERE = Path(__file__).resolve().parent
PACKAGE = Path(os.environ.get('VECTOR_TEST_PACKAGE', HERE/'package'))
sys.path.insert(0, str(PACKAGE))
import vector_stage as v
from gold_io import canonical, digest, Stop
from lawrag.pipeline import oracle_migration as migration
from semantic_runtime.oracle_dp_io import COLUMNS


def corpus(path, texts):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT,PRIMARY KEY(document_id,unit_id))')
        db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d','u',None,canonical({'id':'u','parent':None,'title':'시험 조문','span':[0,len(texts)]})))
        db.execute('CREATE TABLE block_payload(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT,json_text_elided INTEGER,PRIMARY KEY(document_id,block_id))')
        for i, text in enumerate(texts):
            db.execute('INSERT INTO block_payload VALUES(?,?,?,?,?,?,?)', ('d','b%04d'%i,'u',text,'a'*64,'{}',1))
    folder=path.parent/'navigation';folder.mkdir()
    with sqlite3.connect(folder/'navigation.sqlite') as db:
        db.execute('CREATE TABLE source(id TEXT PRIMARY KEY,json TEXT)')
        for off in range(0,len(texts)):
            sid='article:'+hashlib.sha256(str(off).encode()).hexdigest()[:24]
            source={'id':sid,'document_id':'d','unit_id':'u','document_name':'법령',
                    'blocks':[{'block_id':'b%04d'%i} for i in range(off,min(off+1,len(texts)))]}
            db.execute('INSERT INTO source VALUES(?,?)',(sid,canonical(source)))


@pytest.fixture
def runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(v,'STOP_REQUESTED',False)
    monkeypatch.setattr(v,'MAX_ROWS',32)
    old=tmp_path/'old';old.mkdir()
    root=tmp_path/'generation';root.mkdir()
    corpus(root/'store.sqlite',['법령 한글😀 '+str(i) for i in range(60)])
    (root/'manifest.json').write_text('{}')
    contract=v.Contract(PACKAGE/'contract.json')
    directory=tmp_path/('gold-shape-'+contract.sha256[:12]);directory.mkdir()
    source={'dataset_version':'a'*64,'source_manifest':{'scope':{'document_version_ids':['d']},'navigation':{'path':'navigation'}},
            'source_rows':{'block_payload':{'rows':60}}}
    query={'tables':{'test':{'rows':3}}}
    objects=[{'OWNER':t['owner'],'OBJECT_NAME':t['name'],'OBJECT_ID':i,'DATA_OBJECT_ID':i}
             for i,t in enumerate(contract.tables.values())]
    objects.sort(key=lambda r:(r['OWNER'],r['OBJECT_NAME']))
    binding={'code':v.loader.read(PACKAGE/'VECTOR_PARENTS.json')['parents'][0]['code_binding'],
             'contract':contract.sha256,'generation':str(root),'files':{'store.sqlite':'frozen','navigation/navigation.sqlite':'nav-frozen'},
             'database':[{'LOGIN_USER':'fixture','DB_NAME':'fixture','SERVICE_NAME':'fixture'}], 'objects':objects,
             'source_release':digest(source),'query_release':digest(query)}
    prior={'binding':binding,'status':'LOADED_INSERT_ACK','pending':None,'source':{'block_payload':{'rows':60}},
           'query':{'test':{'rows':3,'complete':True}}}
    v.loader.atomic(directory/'state.json',prior)
    c={'embed':0,'db_writes':0,'reads':[],'items':{},'posts':{},'fail_write':None,'fail_model':None,'db_wrong':False,'resets':0,'active_old':False,'fail_reset':False,'stop_embed':False,'stop_write':False}
    class DB:
        _g8_transport=True  # This fixture models the installed transport boundary.
        def __init__(self,*a):pass
        def close(self):pass
        def query(self,sql,**kwargs):
            c['reads'].append(sql)
            if 'SYS_CONTEXT' in sql:return [] if c['db_wrong'] else binding['database']
            if 'ALL_OBJECTS' in sql:return [r for r in objects if 'VCTR_' in r['OBJECT_NAME']]
            pytest.fail('unexpected DB read: '+sql)
        def block(self,sql,binds=(),**kwargs):
            assert kwargs=={'transaction_managed':True}
            if 'DELETE FROM' in sql:
                assert 'TRUNCATE' not in sql and 'WHERE VCTR_POST_ID=:p' in sql
                if c['active_old']:raise RuntimeError('VECTOR_RESET_ACTIVE_PUBLICATION')
                c['resets']+=1
                if c['fail_reset']:
                    c['fail_reset']=False
                    raise RuntimeError('reset ack lost')
                return .01
            assert not any(s in sql for s in ['COUNT(', 'DBMS_LOB.COMPARE','VECTOR_DISTANCE','NOT EXISTS'])
            args={n:x for n,x,_ in binds};rows=json.loads(args['payload'])
            is_item='dim' in args
            key='items' if is_item else 'posts'
            mode=c['fail_write'];c['fail_write']=None
            if mode=='before':raise RuntimeError('before commit')
            if mode=='partial':rows=rows[:1]
            c['db_writes']+=1
            for row in rows:
                if is_item:ident=(row['VCTR_POST_ID'],row['VCTR_SEG_ID'])
                else:ident=row['c0']
                assert ident not in c[key], 'duplicate insertion'
                c[key][ident]=row
            if mode in {'after','partial'}:raise RuntimeError('ack lost')
            if c['stop_write']:c['stop_write']=False;v.STOP_REQUESTED=True
            return .01
    monkeypatch.setattr(v.loader,'Database',DB)
    monkeypatch.setattr(v.loader,'resource_check',lambda p:None)
    monkeypatch.setattr(v,'inputs',lambda *a:(root,binding['files'],source,query,['test']))
    def pending_count(self,db,key,rows):
        c['reads'].append('PENDING_KEYS_ONLY')
        return sum(((r['VCTR_POST_ID'],r['VCTR_SEG_ID']) in c['items']) if key=='VCTR_ITEM'
                   else r['VCTR_POST_ID'] in c['posts'] for r in rows)
    monkeypatch.setattr(v.Contract,'pending_count',pending_count)
    monkeypatch.setattr(v.Contract,'preflight',lambda *a:pytest.fail('full schema preflight'))
    monkeypatch.setattr(migration,'source_binding',lambda *a:pytest.fail('full file hash'))
    monkeypatch.setattr(migration,'source_counts',lambda *a:pytest.fail('source pre-count'))
    def encode(project,config,texts):
        c['embed']+=1
        if c['fail_model']==c['embed']:raise RuntimeError('unknown model response')
        if c['stop_embed']:c['stop_embed']=False;v.STOP_REQUESTED=True
        return [[.6,.8] for _ in texts]
    monkeypatch.setattr(v,'encode',encode)
    monkeypatch.setitem(sys.modules,'dataiku',NS(SQLExecutor2=lambda **kw:None,
        api_client=lambda:NS(get_default_project=lambda:None)))
    monkeypatch.setenv('LEGAL_EMBED_LLM_ID','fixture');monkeypatch.setenv('LEGAL_EMBED_DIMENSIONS','2')
    return NS(old=old,root=root,directory=directory,prior=prior,source=source,query=query,c=c)


def state(rt):return v.loader.read(next((rt.directory/'vectors-structure-r4').glob('*/state.json')))


def state_path(rt):return next((rt.directory/'vectors-structure-r4').glob('*/state.json'))


def test_full_entrypoint_plan_reset_insert_repeat(runtime):
    r=runtime;before=(r.directory/'state.json').read_bytes()
    v.execute(r.old)
    assert len(r.c['items'])==60 and len(r.c['posts'])==1
    assert r.c['embed']==4 and r.c['db_writes']==3 and r.c['resets']==1
    assert state(r)['planned_total_rows']==60 and state(r)['status']==v.COMPLETE
    assert not list(state_path(r).parent.glob('embed-*.json'))
    v.execute(r.old)
    assert r.c['embed']==4 and r.c['db_writes']==3 and r.c['resets']==1
    assert (r.directory/'state.json').read_bytes()==before


@pytest.mark.parametrize('when',['before','after'])
def test_uncertain_write_reuses_cache_pending_keys(runtime,when):
    r=runtime;r.c['fail_write']=when
    with pytest.raises(RuntimeError):v.execute(r.old)
    assert r.c['embed']==2 and state(r)['pending']
    deadline=state(r)['deadline']
    v.execute(r.old)
    assert len(r.c['items'])==60 and r.c['embed']==4 and r.c['resets']==1
    assert r.c['reads'].count('PENDING_KEYS_ONLY')==1
    assert state(r)['deadline']==deadline


def test_partial_write_rejected_without_reembedding(runtime):
    r=runtime;r.c['fail_write']='partial'
    with pytest.raises(RuntimeError):v.execute(r.old)
    marker=state(r)['pending']
    with pytest.raises(Stop,match='PARTIAL_KEYS'):v.execute(r.old)
    assert state(r)['pending']==marker and r.c['embed']==2


@pytest.mark.parametrize('number',[1,2,4])
def test_unknown_model_never_retransmits(runtime,number):
    r=runtime;r.c['fail_model']=number
    with pytest.raises(RuntimeError):v.execute(r.old)
    before=state(r)
    with pytest.raises(Stop,match='OUTCOME_UNKNOWN'):v.execute(r.old)
    assert r.c['embed']==number and state(r)['embedding_pending']==before['embedding_pending']


@pytest.mark.parametrize('kind',['deadline','budget','cache','plan'])
def test_limits_integrity_before_new_model(runtime,kind):
    r=runtime;r.c['fail_write']='before'
    with pytest.raises(RuntimeError):v.execute(r.old)
    p=state_path(r);s=state(r)
    if kind=='deadline':s['deadline']=1
    elif kind=='budget':s['max_calls']=2
    elif kind=='cache':
        q=p.parent/'embed-00000000.json';d=v.loader.read(q);d['vectors'][0]=[0.,1.];v.loader.atomic(q,d)
    else:
        with sqlite3.connect(p.parent/'segment-plan.sqlite') as db:
            db.execute("UPDATE source SET sha='changed'")
    v.loader.atomic(p,s)
    with pytest.raises(Stop,match={'deadline':'DEADLINE','budget':'BUDGET','cache':'CACHE_CONFLICT','plan':'PLAN_CONTENT_CHANGED'}[kind]):v.execute(r.old)
    assert r.c['embed']==2


@pytest.mark.parametrize('stage',['embed','write'])
def test_graceful_stop_preserves_current_receipt(runtime,stage):
    r=runtime;r.c['stop_'+stage]=True
    with pytest.raises(Stop,match='USER_STOPPED'):v.execute(r.old)
    before=state(r)
    assert before['embedding_pending'] is None and before['pending'] is None
    if stage=='embed':assert r.c['embed']==1 and before['rows']==0
    else:assert r.c['embed']==2 and before['rows']==32
    v.STOP_REQUESTED=False
    v.execute(r.old)
    assert r.c['embed']==4 and len(r.c['items'])==60 and r.c['resets']==1
    assert state(r)['deadline']==before['deadline']


def test_reset_ack_loss_is_idempotent_and_does_not_embed(runtime):
    r=runtime;r.c['fail_reset']=True
    with pytest.raises(RuntimeError,match='reset ack lost'):v.execute(r.old)
    assert r.c['embed']==0
    v.execute(r.old)
    assert r.c['resets']==2 and len(r.c['items'])==60


def test_reset_refuses_active_previous_publication(runtime):
    r=runtime;r.c['active_old']=True
    with pytest.raises(RuntimeError,match='ACTIVE_PUBLICATION'):v.execute(r.old)
    assert r.c['embed']==0 and r.c['resets']==0 and r.c['db_writes']==0


def test_exact_old_cache_removed_and_other_work_preserved(runtime):
    r=runtime
    previous={'schema_version':'gold-vector-manifest-preview-v1','query_id':digest(r.query),
              'source_release_id':digest(r.source),'dataset_version':r.source['dataset_version'],
              'documents':['d'],'profile':v.settings(),
              'segment_profile':'navigation-source-block-text-window800-step700-v1'}
    p=r.directory/'vectors-fast-r1'/digest(previous);p.mkdir(parents=True)
    v.loader.atomic(p/'state.json',{'binding':{'manifest':previous},'rows':48000})
    (p/'embed-00000000.json').write_text('prior cache')
    other=p.parent/'unrelated';other.mkdir();(other/'keep').write_text('keep')
    v.execute(r.old)
    assert not p.exists() and (other/'keep').read_text()=='keep'
    assert v.loader.read(state_path(r).parent/'previous-vector-state.json')['rows']==48000
    assert {key[0] for key in r.c['items']}!={digest(previous)}


def test_plan_failure_precedes_deletion_and_model(runtime):
    r=runtime
    with sqlite3.connect(r.root/'store.sqlite') as db:
        db.execute('DELETE FROM source_unit')
    with pytest.raises(Stop,match='STRUCTURE_UNIT_MISSING'):v.execute(r.old)
    assert r.c['resets']==0 and r.c['embed']==0 and r.c['db_writes']==0


def test_lock_and_check_are_nonwriting(runtime):
    r=runtime
    v.execute(r.old,'check')
    assert r.c['resets']==0 and r.c['embed']==0
    with (r.directory/'job.lock').open('a') as f:
        fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):v.execute(r.old)
    assert not (r.directory/'vectors-structure-r4').exists()


def structure_case(tmp_path,blocks,units):
    path=tmp_path/'store.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT,PRIMARY KEY(document_id,unit_id))')
        for uid,parent,label in units:
            db.execute('INSERT INTO source_unit VALUES(?,?,?,?)',('d',uid,parent,canonical({'id':uid,'parent':parent,'title':label})))
        db.execute('CREATE TABLE block_payload(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT,json_text_elided INTEGER,PRIMARY KEY(document_id,block_id))')
        for index,(uid,body) in enumerate(blocks):
            db.execute('INSERT INTO block_payload VALUES(?,?,?,?,?,?,?)',('d',str(index),uid,body,'a'*64,'{}',1))
    return migration.source_open(path),{'id':'article:test','document_id':'d','document_name':'규정',
           'unit_id':units[0][0] if units else None,'heading':'구조 없는 원문',
           'blocks':[{'block_id':str(i)} for i in range(len(blocks))]}


def assert_coverage(items,blocks):
    for index,(_,body) in enumerate(blocks):
        spans=[s for i in items for s in i['meta']['body_spans'] if s['block_id']==str(index)]
        assert spans[0]['start']==0 and spans[-1]['end']==len(body)
        assert all(a['end']==b['start'] for a,b in zip(spans,spans[1:]))
        assert ''.join(body[s['start']:s['end']] for s in spans)==body


def test_short_article_preserves_all_children_whole(tmp_path):
    from structure_segments import source_segments
    blocks=[('a','제1조 적용한다.'),('b','① 조건이다.'),('c','1. 항목이다.'),('a','다만 예외이다.')]
    db,source=structure_case(tmp_path,blocks,[('a',None,'제1조'),('b','a','제1항'),('c','b','제1호')])
    try:items=source_segments(db,source,'v',migration)
    finally:db.close()
    assert len(items)==1 and items[0]['meta']['extent']=='source'
    assert all(t in items[0]['text'] for _,t in blocks)
    assert_coverage(items,blocks)


def test_long_article_split_on_stored_children_keeps_parent_exception(tmp_path):
    from structure_segments import source_segments, POLICY
    blocks=[('a','적용 조건이다.'),('b','첫째 항의 내용. '*12),('c','둘째 항의 내용. '*12),('a','다만 예외는 제외한다.')]
    db,source=structure_case(tmp_path,blocks,[('a',None,'제1조'),('b','a','제1항'),('c','a','제2항')])
    try:items=source_segments(db,source,'v',migration,dict(POLICY,max_input_chars=200))
    finally:db.close()
    child=[i for i in items if i['meta']['unit_id'] in ('b','c')]
    assert len(child)==2
    assert all('적용 조건이다.' in i['text'] and '다만 예외는 제외한다.' in i['text'] for i in child)
    assert_coverage(items,blocks)


def test_long_leaf_splits_sentences_without_losing_tail(tmp_path):
    from structure_segments import source_segments,POLICY
    blocks=[('a',('완전한 문장입니다. 다음 문장입니다!\n'*30)+'마지막 예외입니다.')]
    db,source=structure_case(tmp_path,blocks,[('a',None,'제1조')])
    try:items=source_segments(db,source,'v',migration,dict(POLICY,max_input_chars=160))
    finally:db.close()
    assert len(items)>1 and all(len(i['text'])<=160 for i in items)
    assert '마지막 예외입니다.' in items[-1]['text']
    assert_coverage(items,blocks)


def test_unstructured_source_is_preserved_and_labelled(tmp_path):
    from structure_segments import source_segments
    blocks=[(None,'별도의 원문입니다.')]
    db,source=structure_case(tmp_path,blocks,[])
    try:items=source_segments(db,source,'v',migration)
    finally:db.close()
    assert len(items)==1 and '별도의 원문입니다.' in items[0]['text']
    assert items[0]['meta']['unit_id'] is None and items[0]['meta']['structure_status']=='UNSTRUCTURED'
    assert_coverage(items,blocks)


def test_resume_every_structural_boundary(runtime):
    r=runtime;db=migration.source_open(r.root/'store.sqlite');nav=migration.source_open(r.root/'navigation/navigation.sqlite')
    try:
        whole=list(v.segments(db,nav,r.source['dataset_version'],migration))
        for index,item in enumerate(whole):
            assert list(v.segments(db,nav,r.source['dataset_version'],migration,item['cursor']))==whole[index+1:]
    finally:db.close();nav.close()


def test_sdk_explicit_overflow_fail_and_long_complete_unit():
    from mesh_embedding import encode
    options=[];texts=[]
    def request(**kwargs):
        options.append(kwargs)
        return NS(add_text=texts.append,execute=lambda:NS(get_embeddings=lambda:[[.6,.8]]))
    assert encode(NS(get_llm=lambda _:NS(new_embeddings=request)),{'model':'fixture','dimensions':2},['법'*2000])==[[.6,.8]]
    assert options==[{'text_overflow_mode':'FAIL'}] and len(texts[0])==2000


@pytest.mark.parametrize('vectors',[[[1,2,3]],[[0,0]],[[float('nan'),1]],[]])
def test_sdk_invalid_response_rejected(vectors):
    from mesh_embedding import encode
    project=NS(get_llm=lambda _:NS(new_embeddings=lambda **kw:NS(add_text=lambda _:None,execute=lambda:NS(get_embeddings=lambda:vectors))))
    with pytest.raises(ValueError):encode(project,{'model':'f','dimensions':2},['원문'])


def test_progress_remaining_time_percent_and_kst():
    from vector_progress import render
    text=render({'phase':'VECTOR_PROGRESS','rows':100,'total_rows':1000,'rows_per_second':10,
                 'remaining_seconds':90,'run_seconds':10})
    assert '10.00%' in text and '1분 30초' in text and 'KST' in text and '900행' in text


def test_eta_uses_only_rows_added_since_resume(runtime,monkeypatch):
    r=runtime;r.c['fail_write']='before'
    with pytest.raises(RuntimeError):v.execute(r.old)
    binding=state(r)['binding'];events=[]
    job=v.VectorJob(None,v.Contract(PACKAGE/'contract.json'),state_path(r).parent,binding,
                    NS(emit=lambda phase,**kw:events.append((phase,kw))))
    job.total=1000;job.initial_rows=400;job.state['rows']=500;job.started=10
    monkeypatch.setattr(v.time,'monotonic',lambda:20)
    job.report()
    value=events[-1][1]
    assert value['rows_per_second']==10 and value['remaining_seconds']==50


def test_parent_cycle_and_missing_unit_are_not_inferred(tmp_path):
    from structure_segments import source_segments
    db,source=structure_case(tmp_path,[('a','원문')],[('a','b','제1조'),('b','a','제2조')])
    try:
        with pytest.raises(Stop,match='STRUCTURE_CYCLE'):source_segments(db,source,'v',migration)
    finally:db.close()


def test_original_source_change_refused_before_reset_or_embedding(runtime):
    r=runtime;r.c['fail_write']='before'
    with pytest.raises(RuntimeError):v.execute(r.old)
    (r.root/'manifest.json').write_text('{"changed":true}')
    with pytest.raises(Stop,match='BINDING_CHANGED'):v.execute(r.old)
    assert r.c['embed']==2 and r.c['resets']==1


@pytest.mark.parametrize('exit_code',[0,1])
def test_delivered_notebook_exact_zip_and_progress(tmp_path,monkeypatch,exit_code):
    script=(HERE/'DATAIKU_GOLD_VECTOR_STRUCTURE_RUN_R4.txt').read_text()
    archive=HERE/'DATAIKU_GOLD_VECTOR_STRUCTURE_20261104_R4.zip'
    old=tmp_path/'old';old.mkdir()
    script=script.replace('OLD_JOB_DIR = ""','OLD_JOB_DIR = '+repr(str(old)),1)
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path));monkeypatch.chdir(tmp_path)
    folder=NS(list_paths_in_partition=lambda:['/'+archive.name],get_download_stream=lambda name:io.BytesIO(archive.read_bytes()))
    monkeypatch.setitem(sys.modules,'dataiku',NS(Folder=lambda name:folder))
    original=subprocess.Popen;calls=[]
    def launch(args,**kwargs):
        calls.append(args)
        assert Path(args[2]).read_bytes()==(HERE/'package/vector_stage.py').read_bytes()
        code="import json;print(json.dumps({'phase':'VECTOR_PLAN_COMPLETE','total_rows':60,'total_sources':60}));print(json.dumps({'phase':'"+('DIAGNOSTIC_ERROR' if exit_code else v.COMPLETE)+"','rows':60}));raise SystemExit("+str(exit_code)+")"
        return original([sys.executable,'-u','-c',code],**kwargs)
    monkeypatch.setattr(subprocess,'Popen',launch)
    namespace={};exec(compile(script,'notebook','exec'),namespace)
    assert namespace['VECTOR_RESULT']['process_exit']==exit_code
    assert namespace['VECTOR_RESULT']['status']==('FAILED_OR_STOPPED' if exit_code else 'COMPLETE')
    assert len(calls)==1
    assert '전체 적재 대상 확정: 60벡터' in next((tmp_path/'gold-progress-logs').glob('*.log')).read_text()


def test_notebook_group_interrupt_preserves_worker_checkpoint(tmp_path):
    # Interrupt a real notebook process group. The worker must receive its
    # graceful request, finish the in-flight result, and exit on its own.
    old=tmp_path/'old';old.mkdir()
    ready=tmp_path/'worker-ready';saved=tmp_path/'response-saved'
    archive=HERE/'DATAIKU_GOLD_VECTOR_STRUCTURE_20261104_R4.zip'
    worker="""import signal,time
from pathlib import Path
stopped=False
def stop(signum,frame):
    global stopped
    stopped=True
signal.signal(signal.SIGUSR1,stop)
Path(%r).write_text('ready')
deadline=time.monotonic()+8
while not stopped and time.monotonic()<deadline:time.sleep(.01)
if not stopped:raise SystemExit(2)
Path(%r).write_text('complete-response')
print('VECTOR_USER_STOPPED_RESUME_AVAILABLE',flush=True)
""" % (str(ready),str(saved))
    harness="""import io,sys,tempfile,subprocess
from pathlib import Path
from types import SimpleNamespace as NS
archive=Path(%r)
folder=NS(list_paths_in_partition=lambda:['/'+archive.name],get_download_stream=lambda name:io.BytesIO(archive.read_bytes()))
sys.modules['dataiku']=NS(Folder=lambda name:folder)
tempfile.gettempdir=lambda:%r
original=subprocess.Popen
def launch(args,**kwargs):return original([sys.executable,'-u','-c',%r],**kwargs)
subprocess.Popen=launch
script=Path(%r).read_text().replace('OLD_JOB_DIR = ""','OLD_JOB_DIR = '+repr(%r),1)
exec(compile(script,'notebook','exec'),{})
""" % (str(archive),str(tmp_path),worker,str(HERE/'DATAIKU_GOLD_VECTOR_STRUCTURE_RUN_R4.txt'),str(old))
    process=subprocess.Popen([sys.executable,'-u','-c',harness],cwd=str(tmp_path),
                             start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    try:
        deadline=time.monotonic()+8
        while not ready.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.01)
        assert ready.exists()
        os.killpg(process.pid,signal.SIGINT)
        output=process.communicate(timeout=10)[0].decode()
        assert process.returncode==0,output
        assert saved.read_text()=='complete-response'
        assert 'VECTOR_USER_STOPPED_RESUME_AVAILABLE' in next((tmp_path/'gold-progress-logs').glob('*.log')).read_text()
        assert 'KeyboardInterrupt' not in output
    finally:
        if process.poll() is None:
            process.kill();process.wait()


@pytest.mark.parametrize('pattern',['가','긴 문장 원문 ','항목, 내용; 값: ','한😀e\u0301👩\u200d💻'])
def test_field_size_long_leaf_is_lossless_and_bounded(tmp_path,pattern):
    from structure_segments import source_segments
    heading='규정 / 제1조\n'
    body=(pattern*50000)[:42336-len(heading)]
    blocks=[('a',body)]
    db,source=structure_case(tmp_path,blocks,[('a',None,'제1조')])
    try:items=source_segments(db,source,'v',migration)
    finally:db.close()
    assert len(items)>5 and all(0<len(i['text'])<=8000 for i in items)
    assert len({i['id'] for i in items})==len(items)
    assert_coverage(items,blocks)
    assert [i['meta']['source_segment_index'] for i in items]==list(range(len(items)))
    assert all(i['meta']['source_segment_count']==len(items) and i['meta']['source_id']==source['id'] for i in items)
    for item in items:
        span=item['meta']['body_spans'][0]
        assert item['text'].endswith(body[span['start']:span['end']])


def test_long_parent_and_child_preserve_full_source_links(tmp_path):
    from structure_segments import source_segments
    blocks=[('a','부모조건'*9000),('b','자식 적용문장. '*2000),('a','다만 마지막 예외는 적용하지 않는다.')]
    db,source=structure_case(tmp_path,blocks,[('a',None,'제1조'),('b','a','제1항')])
    try:items=source_segments(db,source,'v',migration)
    finally:db.close()
    assert all(len(i['text'])<=8000 for i in items)
    assert_coverage(items,blocks)
    children=[i for i in items if i['meta']['unit_id']=='b']
    assert children and all(i['meta']['context_mode']=='LINKED_REMAINDER' for i in children)
    assert all(i['meta']['context_scope_units']==['a'] for i in children)
    assert all('다만 마지막 예외는 적용하지 않는다.' in i['text'] for i in children)


def test_long_heading_retained_in_metadata_and_body_not_lost(tmp_path):
    from structure_segments import source_segments
    label='아주 긴 제목'*8000
    db,source=structure_case(tmp_path,[('a','실제 본문')],[('a',None,label)])
    try:items=source_segments(db,source,'v',migration)
    finally:db.close()
    assert len(items)==1 and len(items[0]['text'])<=8000
    assert label in items[0]['meta']['full_structure_heading']
    assert items[0]['text'].endswith('실제 본문')


def test_long_field_sized_input_runs_through_plan_model_and_db(runtime):
    r=runtime
    with sqlite3.connect(r.root/'store.sqlite') as db:
        db.execute('UPDATE block_payload SET text=? WHERE block_id=?',('원'*42336,'b0000'))
    v.execute(r.old)
    s=state(r)
    assert s['status']==v.COMPLETE and s['rows']==s['planned_total_rows'] and s['rows']>60
    assert len(r.c['items'])==s['rows'] and r.c['resets']==1
    calls=r.c['embed'];v.execute(r.old)
    assert r.c['embed']==calls and r.c['resets']==1


def make_previous_r3(r):
    r.c['active_old']=True
    with pytest.raises(RuntimeError,match='ACTIVE_PUBLICATION'):v.execute(r.old)
    value=state(r);shutil.rmtree(state_path(r).parent)
    parent=v.loader.read(PACKAGE/'VECTOR_STRUCTURE_PARENT.json')
    value['binding']['code']=parent['code_binding']
    value['binding']['manifest']['segment_profile']=parent['policy']
    old=r.directory/'vectors-structure-r3'/digest(value['binding']['manifest'])/'state.json'
    old.parent.mkdir(parents=True)
    value['deadline']-=100;value['last_error']={'message':'VECTOR_STRUCTURAL_SENTENCE_TOO_LONG'}
    v.loader.atomic(old,value);r.c['active_old']=False
    return old,value


def test_failed_r3_preparation_carries_original_deadline(runtime):
    old,value=make_previous_r3(runtime)
    before=old.read_bytes()
    v.execute(runtime.old)
    assert old.read_bytes()==before
    assert state(runtime)['deadline']==value['deadline']
    assert state(runtime)['max_calls']==value['max_calls']
    assert (state_path(runtime).parent/'previous-r3-preparation-state.json').read_bytes()==before
    assert runtime.c['embed']==4 and runtime.c['resets']==1


@pytest.mark.parametrize('kind',['unknown','rows','binding','expired'])
def test_r3_unsafe_or_expired_predecessor_stops_before_external_work(runtime,kind):
    old,value=make_previous_r3(runtime)
    if kind=='unknown':value.update(embedding_calls=1,embedding_pending={'batch':0})
    elif kind=='rows':value['rows']=1
    elif kind=='binding':value['binding']['code']='unrecognized'
    else:value['deadline']=0
    v.loader.atomic(old,value)
    with pytest.raises(Stop,match={'unknown':'HAS_EXTERNAL_WORK','rows':'HAS_EXTERNAL_WORK','binding':'R3_PREPARATION_BINDING_CHANGED','expired':'DEADLINE'}[kind]):v.execute(runtime.old)
    assert runtime.c['embed']==0 and runtime.c['resets']==0 and runtime.c['db_writes']==0


def test_dashboard_throttles_escapes_and_requires_completion_marker(monkeypatch):
    import notebook_progress as n
    clock=[10.];monkeypatch.setattr(n.time,'monotonic',lambda:clock[0])
    frames=[]
    p=n.Panel('vector','<model>',1024,'/nfs','/logs',publish=lambda html,plain:frames.append((html,plain)))
    for index in range(1000):
        p.consume(json.dumps({'phase':'VECTOR_PROGRESS','rows':index,'total_rows':1000,
                             'rows_per_second':10,'remaining_seconds':100,'run_seconds':1,'sdk_calls':50}))
    assert len(frames)==1
    clock[0]+=2;p.update()
    assert len(frames)==2 and '999/1,000' in frames[-1][1] and '&lt;model&gt;' in frames[-1][0]
    assert p.finish(0)['status']=='FAILED_OR_STOPPED'
    p.consume(json.dumps({'phase':'DIAGNOSTIC_ERROR','causes':[{'type':'Stop','message':'<script>오류</script>'}]}))
    assert '&lt;script&gt;오류&lt;/script&gt;' in frames[-1][0] and '<script>' not in frames[-1][0]


def test_dashboard_success_and_error_remain_in_same_publisher():
    from notebook_progress import Panel
    frames=[];p=Panel('vector','model',1024,'/nfs','/log',publish=lambda h,t:frames.append((h,t)))
    p.consume(json.dumps({'phase':v.COMPLETE,'rows':100}))
    assert p.finish(0)['status']=='COMPLETE'
    assert '100.00%' in frames[-1][1] and '서비스 활성화 별도' in frames[-1][1]
    p.consume(json.dumps({'phase':'DIAGNOSTIC_ERROR','causes':[{'type':'Stop','message':'actual failure'}]}))
    assert p.finish(1)['status']=='FAILED_OR_STOPPED' and 'actual failure' in frames[-1][1]
