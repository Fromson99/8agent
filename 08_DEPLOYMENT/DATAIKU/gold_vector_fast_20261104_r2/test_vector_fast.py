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
        db.execute('CREATE TABLE block_payload(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT,json TEXT,json_text_elided INTEGER,PRIMARY KEY(document_id,block_id))')
        for i, text in enumerate(texts):
            db.execute('INSERT INTO block_payload VALUES(?,?,?,?,?,?,?)', ('d','b%04d'%i,'u',text,'a'*64,'{}',1))
    folder=path.parent/'navigation';folder.mkdir()
    with sqlite3.connect(folder/'navigation.sqlite') as db:
        db.execute('CREATE TABLE source(id TEXT PRIMARY KEY,json TEXT)')
        for off in range(0,len(texts),7):
            sid='article:'+hashlib.sha256(str(off).encode()).hexdigest()[:24]
            source={'id':sid,'document_id':'d','unit_id':'u','document_name':'법령',
                    'blocks':[{'block_id':'b%04d'%i} for i in range(off,min(off+7,len(texts)))]}
            db.execute('INSERT INTO source VALUES(?,?)',(sid,canonical(source)))


def test_segment_resume_every_boundary_and_exact_original(tmp_path):
    path=tmp_path/'store.sqlite'
    texts=['', ' '*900, '가'*801, '법😀'*1200, 'x'*1501, 'tail']
    corpus(path,texts)
    db=migration.source_open(path)
    nav=migration.source_open(path.parent/'navigation/navigation.sqlite')
    try:
        whole=list(v.segments(db,nav,'a'*64,migration))
        for index,item in enumerate(whole):
            assert list(v.segments(db,nav,'a'*64,migration,item['cursor'])) == whole[index+1:]
            body=texts[int(item['meta']['block_id'][1:])]
            assert body[item['meta']['start']:item['meta']['end']]==item['text']
            s=json.loads(nav.execute('SELECT json FROM source WHERE id=?',(item['meta']['source_id'],)).fetchone()[0])
            assert item['meta']['source_sha256']==digest(s)
        trace=[];db.set_trace_callback(trace.append)
        list(v.segments(db,nav,'a'*64,migration,whole[-2]['cursor']))
        assert all('COUNT(' not in s.upper() for s in trace)
        assert all('WHERE' in s.upper() for s in trace if s.startswith('SELECT *'))
    finally:db.close();nav.close()


@pytest.fixture
def runtime(tmp_path,monkeypatch):
    old=tmp_path/'old';old.mkdir()
    root=tmp_path/'generation';root.mkdir()
    corpus(root/'store.sqlite',['법령 한글😀 '+str(i) for i in range(150)])
    (root/'manifest.json').write_text('{}')
    contract=v.Contract(PACKAGE/'contract.json')
    directory=tmp_path/('gold-shape-'+contract.sha256[:12]);directory.mkdir()
    source={'dataset_version':'a'*64,'source_manifest':{'scope':{'document_version_ids':['d']},'navigation':{'path':'navigation'}},
            'source_rows':{'block_payload':{'rows':150}}}
    query={'tables':{'test':{'rows':3}}}
    objects=[{'OWNER':t['owner'],'OBJECT_NAME':t['name'],'OBJECT_ID':i,'DATA_OBJECT_ID':i}
             for i,t in enumerate(contract.tables.values())]
    objects.sort(key=lambda r:(r['OWNER'],r['OBJECT_NAME']))
    binding={'code':v.loader.read(PACKAGE/'VECTOR_PARENTS.json')['parents'][0]['code_binding'],
             'contract':contract.sha256,'generation':str(root),'files':{'store.sqlite':'frozen','navigation/navigation.sqlite':'nav-frozen'},
             'database':[{'LOGIN_USER':'fixture','DB_NAME':'fixture','SERVICE_NAME':'fixture'}], 'objects':objects,
             'source_release':digest(source),'query_release':digest(query)}
    prior={'binding':binding,'status':'LOADED_INSERT_ACK','pending':None,'source':{'block_payload':{'rows':150}},
           'query':{'test':{'rows':3,'complete':True}}}
    v.loader.atomic(directory/'state.json',prior)
    c={'embed':0,'db_writes':0,'reads':[],'items':{},'posts':{},'fail_write':None,'fail_model':None,'db_wrong':False}
    class DB:
        _g8_transport=True  # This fixture models the installed transport boundary.
        def __init__(self,*a):pass
        def close(self):pass
        def query(self,sql,**kwargs):
            c['reads'].append(sql)
            if 'SYS_CONTEXT' in sql:return [] if c['db_wrong'] else binding['database']
            if 'ALL_OBJECTS' in sql:return [r for r in objects if 'VCTR_ITEM' in r['OBJECT_NAME'] or 'VCTR_POST' in r['OBJECT_NAME']]
            pytest.fail('unexpected DB read: '+sql)
        def block(self,sql,binds=(),**kwargs):
            assert kwargs=={'transaction_managed':True}
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
        return [[.6,.8] for _ in texts]
    monkeypatch.setattr(v,'encode',encode)
    monkeypatch.setitem(sys.modules,'dataiku',NS(SQLExecutor2=lambda **kw:None,
        api_client=lambda:NS(get_default_project=lambda:None)))
    monkeypatch.setenv('LEGAL_EMBED_LLM_ID','fixture');monkeypatch.setenv('LEGAL_EMBED_DIMENSIONS','2')
    return NS(old=old,root=root,directory=directory,prior=prior,source=source,query=query,c=c)


def state(rt):return v.loader.read(next((rt.directory/'vectors-fast-r1').glob('*/state.json')))


def test_actual_entrypoint_success_repeat_parent_unchanged(runtime):
    r=runtime;before=(r.directory/'state.json').read_bytes()
    v.execute(r.old)
    assert len(r.c['items'])==150 and len(r.c['posts'])==1
    assert r.c['embed']==10 and r.c['db_writes']==3
    assert len(r.c['reads'])==2 and state(r)['status']==v.COMPLETE
    assert not list((r.directory/'vectors-fast-r1').glob('*/embed-*.json'))
    v.execute(r.old)
    assert r.c['embed']==10 and r.c['db_writes']==3 and len(r.c['reads'])==4
    assert (r.directory/'state.json').read_bytes()==before
    assert state(r)['full_values_verified'] is False


@pytest.mark.parametrize('when',['before','after'])
def test_uncertain_db_only_pending_keys_and_no_reembedding(runtime,when):
    r=runtime;r.c['fail_write']=when
    with pytest.raises(RuntimeError):v.execute(r.old)
    assert r.c['embed']==8 and state(r)['pending']
    deadline=state(r)['deadline']
    v.execute(r.old)
    assert len(r.c['items'])==150 and r.c['embed']==10
    assert r.c['reads'].count('PENDING_KEYS_ONLY')==1
    assert state(r)['deadline']==deadline


def test_partial_db_keys_stop_preserve_pending(runtime):
    r=runtime;r.c['fail_write']='partial'
    with pytest.raises(RuntimeError):v.execute(r.old)
    before=state(r)['pending']
    with pytest.raises(Stop,match='PARTIAL_KEYS'):v.execute(r.old)
    assert state(r)['pending']==before and len(r.c['items'])==1 and r.c['embed']==8


@pytest.mark.parametrize('number',[1,2,9])
def test_unknown_model_stops_no_retransmit_at_later_batch(runtime,number):
    r=runtime;r.c['fail_model']=number
    with pytest.raises(RuntimeError):v.execute(r.old)
    before=state(r)
    with pytest.raises(Stop,match='OUTCOME_UNKNOWN'):v.execute(r.old)
    assert r.c['embed']==number and state(r)['embedding_pending']==before['embedding_pending']
    assert len(r.c['items'])==(128 if number==9 else 0)


def test_cache_saved_before_intent_clear_recovers(runtime,monkeypatch):
    r=runtime;atomic=v.loader.atomic;failed=[False]
    def crash(path,value):
        if str(path).endswith('embed-00000000.json') and not failed[0]:
            atomic(path,value);failed[0]=True;raise RuntimeError('crash after response cache')
        atomic(path,value)
    monkeypatch.setattr(v.loader,'atomic',crash)
    with pytest.raises(RuntimeError):v.execute(r.old)
    v.execute(r.old)
    assert r.c['embed']==10 and len(r.c['items'])==150


def test_publication_ack_loss_recovers_without_vectors(runtime,monkeypatch):
    r=runtime;original=v.VectorJob.write
    def write(self,key,*args):
        if key=='VCTR_POST' and not r.c['posts']:r.c['fail_write']='after'
        return original(self,key,*args)
    monkeypatch.setattr(v.VectorJob,'write',write)
    with pytest.raises(RuntimeError):v.execute(r.old)
    assert len(r.c['posts'])==1
    v.execute(r.old)
    assert r.c['embed']==10 and r.c['db_writes']==3 and state(r)['status']==v.COMPLETE


def test_source_changed_between_runs_rejected(runtime):
    r=runtime;r.c['fail_write']='before'
    with pytest.raises(RuntimeError):v.execute(r.old)
    (r.root/'manifest.json').write_text('{"changed":true}')
    with pytest.raises(Stop,match='BINDING_CHANGED'):v.execute(r.old)
    assert r.c['embed']==8


@pytest.mark.parametrize('kind',['deadline','budget','cache'])
def test_limits_and_cache_integrity(runtime,kind):
    r=runtime;r.c['fail_write']='before'
    with pytest.raises(RuntimeError):v.execute(r.old)
    path=next((r.directory/'vectors-fast-r1').glob('*/state.json'));s=v.loader.read(path)
    if kind=='deadline':s['deadline']=1
    elif kind=='budget':s['max_calls']=8
    else:
        cache=path.parent/'embed-00000000.json';value=v.loader.read(cache);value['vectors'][0]=[0.,1.];v.loader.atomic(cache,value)
    v.loader.atomic(path,s)
    with pytest.raises(Stop,match={'deadline':'DEADLINE','budget':'BUDGET','cache':'CACHE_CONFLICT'}[kind]):v.execute(r.old)
    assert r.c['embed']==8


def test_check_no_model_or_vector_state(runtime):
    r=runtime;v.execute(r.old,'check')
    assert r.c['embed']==0 and r.c['db_writes']==0
    assert not (r.directory/'vectors-fast-r1').exists()


def test_lock_blocks_concurrent_writer(runtime):
    r=runtime
    with (r.directory/'job.lock').open('a') as f:
        fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):v.execute(r.old)
    assert r.c['embed']==0 and r.c['db_writes']==0


@pytest.mark.parametrize('change',['incomplete','pending','unknown_code','wrong_database','scope'])
def test_wrong_target_incomplete_and_scope_before_model(runtime,change):
    r=runtime;p=copy.deepcopy(r.prior)
    if change=='incomplete':p['status']='LOADING'
    elif change=='pending':p['pending']={'uncertain':True}
    elif change=='unknown_code':p['binding']['code']='unknown'
    elif change=='wrong_database':r.c['db_wrong']=True
    else:
        r.source['source_manifest']['scope']['document_version_ids']=[]
        p['binding']['source_release']=digest(r.source)
    v.loader.atomic(r.directory/'state.json',p)
    with pytest.raises(Stop):v.execute(r.old)
    assert r.c['embed']==0 and r.c['db_writes']==0


def test_sql_fixed_shape_mapping_and_no_readback():
    c=v.Contract(PACKAGE/'contract.json')
    row={'VCTR_POST_ID':'p','VCTR_SEG_ID':'s','DOC_ID':'d','SRC_UNIT_ID':'d:u','VCTR_META_CTNT':'한글😀','EMBD_VCTR_VALU':'[.6,.8]'}
    a,b=v.vector_sql(c,[row],2);x,y=v.vector_sql(c,[dict(row,VCTR_META_CTNT='other')]*128,1024)
    assert a==x and b!=y
    assert 'VCTR_SCTN_ID' in a and 'VCTR_DTLS_IFMN_CTNT' in a and 'EMBD_VCTR' in a
    assert not any(s in a for s in ('COUNT(', 'NOT EXISTS','DBMS_LOB.COMPARE','VECTOR_DISTANCE'))


@pytest.mark.parametrize('vectors',[[[1.,2.,3.]],[[0.,0.]],[[float('nan'),1.]],[]])
def test_mesh_invalid_output_refused(vectors):
    from mesh_embedding import encode
    request=NS(add_text=lambda x:None,execute=lambda:NS(get_embeddings=lambda:vectors))
    project=NS(get_llm=lambda name:NS(new_embeddings=lambda:request))
    with pytest.raises(ValueError):encode(project,{'model':'test','dimensions':2},['text'])


def test_gold_consumer_accepts_sealed_envelope(runtime):
    r=runtime;v.execute(r.old)
    path=HERE.parent.parent/'LOCAL/gold_connection_r12/gold_connection.py'
    spec=importlib.util.spec_from_file_location('vector_gold_consumer',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    post=next(iter(r.c['posts'].values()))
    request=NS(release_id=digest(r.query),snapshot=NS(release_id=digest(r.source),dataset_version=r.source['dataset_version']),
               sql=NS(query=lambda *a,**kw:[{'VCTR_POST_IFMN_CTNT':post['c1']}]))
    reader=module.VectorReader(request,NS(table=lambda key:key))
    assert reader.metadata(post['c0'])['completion']['count']==150


@pytest.mark.parametrize('mode,parent_index',[('full',1),('reduced',0),('reduced',1)])
def test_r7_and_reduced_parent_readonly(runtime,mode,parent_index):
    r=runtime;p=copy.deepcopy(r.prior)
    p['binding']['code']=v.loader.read(PACKAGE/'VECTOR_PARENTS.json')['parents'][parent_index]['code_binding']
    if mode=='reduced':
        r.directory=r.directory.with_name(r.directory.name+'-reduced-r4');r.directory.mkdir()
        p['binding']['projection_policy']='fixture-reduced'
    v.loader.atomic(r.directory/'state.json',p)
    before=(r.directory/'state.json').read_bytes()
    v.execute(r.old)
    assert len(r.c['items'])==150 and (r.directory/'state.json').read_bytes()==before


@pytest.mark.parametrize('when',['before','after'])
def test_payload_boundary_with_cached_next_group_recovery(runtime,monkeypatch,when):
    r=runtime;monkeypatch.setattr(v,'MAX_BYTES',25000)
    r.c['fail_write']=when
    with pytest.raises(RuntimeError):v.execute(r.old)
    v.execute(r.old)
    assert r.c['embed']==10 and len(r.c['items'])==150 and state(r)['status']==v.COMPLETE


@pytest.mark.parametrize('exit_code',[0,1])
def test_complete_delivered_notebook_extracts_and_launches_exact_zip(tmp_path,monkeypatch,exit_code):
    script=(HERE/'DATAIKU_GOLD_VECTOR_FAST_RUN_R2.txt').read_text()
    archive=HERE/'DATAIKU_GOLD_VECTOR_FAST_20261104_R2.zip'
    old=tmp_path/'old';old.mkdir()
    script=script.replace('OLD_JOB_DIR = ""','OLD_JOB_DIR = '+repr(str(old)),1)
    monkeypatch.setattr(tempfile,'gettempdir',lambda:str(tmp_path))
    monkeypatch.chdir(tmp_path)
    folder=NS(list_paths_in_partition=lambda:['/'+archive.name],get_download_stream=lambda name:io.BytesIO(archive.read_bytes()))
    monkeypatch.setitem(sys.modules,'dataiku',NS(Folder=lambda name:folder))
    original=subprocess.Popen;calls=[]
    def launch(args,**kwargs):
        calls.append((args,kwargs))
        assert Path(args[2]).name=='vector_stage.py' and args[3]=='vector'
        assert kwargs['env']['LEGAL_EMBED_LLM_ID']=='openai:genos-embedding:embedding-kure-v1'
        assert kwargs['env']['LEGAL_EMBED_DIMENSIONS']=='1024'
        assert kwargs['env']['G19_OLD_JOB_DIR']==str(old)
        assert Path(args[2]).read_bytes()==(HERE/'package/vector_stage.py').read_bytes()
        return original([sys.executable,'-u','-c',"print('한글 벡터 실행');raise SystemExit("+str(exit_code)+")"],**kwargs)
    monkeypatch.setattr(subprocess,'Popen',launch)
    if exit_code:
        with pytest.raises(RuntimeError,match='벡터 단계 중단'):exec(compile(script,'delivered-notebook','exec'),{})
    else:exec(compile(script,'delivered-notebook','exec'),{})
    assert len(calls)==1
    log=next((tmp_path/'gold-progress-logs').glob('*.log')).read_text()
    assert '한글 벡터 실행' in log and 'PROCESS_EXIT='+str(exit_code) in log


def original_r1():
    path = HERE.parent/'gold_vector_fast_20261103_r1/package/vector_stage.py'
    spec = importlib.util.spec_from_file_location('original_vector_r1', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def old_zip(*args, **kwargs):
    if kwargs:
        raise TypeError('zip() takes no keyword arguments')
    return zip(*args)


def test_python39_failure_then_resume_cached_response(runtime, monkeypatch):
    r = runtime
    original = original_r1()
    monkeypatch.setattr(original, 'zip', old_zip, raising=False)
    prior_code = v.loader.read(PACKAGE/'VECTOR_RESUME_PARENT.json')['code_binding']
    # All I/O follows the real execute entrypoint; inject only R1's rows_for
    # and its exact sealed code binding to create the photographed failure.
    with monkeypatch.context() as first:
        first.setattr(v.loader, 'verify_code', lambda: prior_code)
        first.setattr(v, 'rows_for', original.rows_for)
        with pytest.raises(TypeError, match='zip.*keyword'):
            v.execute(r.old)
    before = state(r)
    path = next((r.directory/'vectors-fast-r1').glob('*/state.json'))
    cache = path.parent/'embed-00000000.json'
    assert cache.is_file() and before['status'] == 'EMBEDDING_CACHED'
    assert r.c['embed'] == 1 and r.c['db_writes'] == 0
    v.execute(r.old)
    after = state(r)
    assert r.c['embed'] == 10 and len(r.c['items']) == 150
    assert after['deadline'] == before['deadline']
    assert after['last_error'] == before['last_error']
    assert after['status'] == v.COMPLETE
    assert len(after['code_upgrades']) == 1
    assert v.loader.read(path.parent/after['code_upgrades'][0]['backup']) == before
    v.execute(r.old)
    assert r.c['embed'] == 10 and r.c['db_writes'] == 3
    assert len(state(r)['code_upgrades']) == 1


@pytest.mark.parametrize('counts', [(1, 0), (0, 1), (1, 2), (2, 1)])
def test_pairing_length_mismatch_never_silently_truncates(counts):
    with pytest.raises(Stop, match='VECTOR_EMBED_COUNT_MISMATCH'):
        v.rows_for('p', [None]*counts[0], [None]*counts[1])


def test_rows_identical_to_r1_without_zip_keywords(monkeypatch):
    original = original_r1()
    items = [{'id': 's', 'meta': {'document_id': 'd', 'source_id': 'u', 'text': '한글😀'}}]
    # Python 3.9 cannot execute R1, so compute its same-length output using
    # a positional zip adapter; mismatch behavior is covered separately.
    monkeypatch.setattr(original, 'zip', lambda a, b, strict: zip(a, b), raising=False)
    monkeypatch.setattr(v, 'zip', old_zip, raising=False)
    assert v.rows_for('p', items, [[.6, .8]]) == original.rows_for('p', items, [[.6, .8]])


@pytest.mark.parametrize('failure', ['unknown', 'db_before', 'db_after'])
def test_r1_upgrade_preserves_pending_and_budget(runtime, monkeypatch, failure):
    r = runtime
    prior_code = v.loader.read(PACKAGE/'VECTOR_RESUME_PARENT.json')['code_binding']
    if failure == 'unknown':
        r.c['fail_model'] = 1
    else:
        r.c['fail_write'] = failure[3:]
    with monkeypatch.context() as first:
        first.setattr(v.loader, 'verify_code', lambda: prior_code)
        with pytest.raises(RuntimeError):
            v.execute(r.old)
    before = state(r)
    if failure == 'unknown':
        with pytest.raises(Stop, match='OUTCOME_UNKNOWN'):
            v.execute(r.old)
        assert r.c['embed'] == 1 and r.c['db_writes'] == 0
        assert state(r)['embedding_pending'] == before['embedding_pending']
    else:
        v.execute(r.old)
        assert r.c['embed'] == 10 and len(r.c['items']) == 150
    assert state(r)['deadline'] == before['deadline']
    assert state(r)['max_calls'] == before['max_calls']


@pytest.mark.parametrize('change', ['unknown_code', 'profile', 'backup_conflict'])
def test_compat_upgrade_rejects_conflict_before_new_model(runtime, monkeypatch, change):
    r = runtime
    parent = v.loader.read(PACKAGE/'VECTOR_RESUME_PARENT.json')
    r.c['fail_model'] = 1
    with monkeypatch.context() as first:
        first.setattr(v.loader, 'verify_code', lambda: parent['code_binding'])
        with pytest.raises(RuntimeError):
            v.execute(r.old)
    path = next((r.directory/'vectors-fast-r1').glob('*/state.json'))
    before = state(r)
    if change == 'unknown_code':
        before['binding']['code'] = 'unapproved'
    elif change == 'profile':
        before['binding']['manifest']['profile']['model'] = 'different'
    else:
        backup = path.parent/('state-before-python-compat-'+parent['code_binding']+'.json')
        v.loader.atomic(backup, {'conflict': True})
    v.loader.atomic(path, before)
    with pytest.raises(Stop, match='BINDING_CHANGED|BACKUP_CONFLICT'):
        v.execute(r.old)
    assert state(r) == before
    assert r.c['embed'] == 1 and r.c['db_writes'] == 0


def test_resume_after_backup_before_state_upgrade_crash(runtime, monkeypatch):
    r = runtime
    parent = v.loader.read(PACKAGE/'VECTOR_RESUME_PARENT.json')
    r.c['fail_write'] = 'before'
    with monkeypatch.context() as first:
        first.setattr(v.loader, 'verify_code', lambda: parent['code_binding'])
        with pytest.raises(RuntimeError):
            v.execute(r.old)
    before = state(r)
    atomic = v.loader.atomic
    with monkeypatch.context() as crash:
        def fail(path, value):
            if Path(path).name == 'state.json' and value.get('code_upgrades'):
                raise OSError('state upgrade interrupted')
            atomic(path, value)
        crash.setattr(v.loader, 'atomic', fail)
        with pytest.raises(OSError, match='interrupted'):
            v.execute(r.old)
    assert state(r) == before and r.c['embed'] == 8
    v.execute(r.old)
    assert state(r)['status'] == v.COMPLETE and r.c['embed'] == 10
