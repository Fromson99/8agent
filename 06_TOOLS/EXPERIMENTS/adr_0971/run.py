"""Single frozen research entry point: corpus, embed, retrieve, rerank, answer."""
from common import *
import os,time,sqlite3,importlib.util,resource,fcntl,traceback
sys.dont_write_bytecode=True
mode=sys.argv[1];freeze=read(DES/'freeze.json');criteria=read(DES/'criteria.json');models=read(DES/'models.json')
for path,h in freeze['files'].items():assert sha(ROOT/path)==h,'Frozen input changed: '+path
for path,h in models['files'].items():assert sha(ROOT/path)==h,'Model changed: '+path
candidate=freeze['candidates'][1];cp=ROOT/candidate['manifest_path'];assert sha(cp)==candidate['manifest_sha256']
for item in read(cp)['revisions'][-1]['files']:assert sha(ROOT/item['frozen_path'])==item['snapshot_sha256']
path=cp.parent/'revisions'/candidate['revision_id']/'snapshot'/TARGET
spec=importlib.util.spec_from_file_location('fulltext_vector_probe',path);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
RUN.mkdir(parents=True,exist_ok=True);lock=(RUN/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
receipt=RUN/(mode+'-receipt.json')
if receipt.exists():raise SystemExit('Stage already complete; preserve immutable receipt')
attempt=len(list(RUN.glob(mode+'-attempt-*.json')))+1
if attempt>1 and (mode!='embed' or attempt>2):raise RuntimeError('Only one bounded embedding resume is authorized by frozen plan')
attempt_path=RUN/f'{mode}-attempt-{attempt:02}.json';put(attempt_path,{'status':'started','at':time.time(),'freeze_sha256':sha(DES/'freeze.json')})
source=ROOT/criteria['generation_path']/'store.sqlite';allowed=set(criteria['scope']);cases=read(DES/'cases.json');corpus=RUN/'corpus.sqlite'
started=time.monotonic()
def local_threads():
    import torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
def embedding_model():
    local_threads()
    from sentence_transformers import SentenceTransformer
    model=SentenceTransformer(str(ROOT/models['embedding']),device='cpu',local_files_only=True,model_kwargs={'use_safetensors':True})
    model.max_seq_length=criteria['chunking']['max_embedding_tokens']
    return model
try:
 if mode=='corpus':
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(str(ROOT/models['embedding']),local_files_only=True)
    stats=p.build(source,allowed,corpus,tok,criteria['chunking']);put(RUN/'corpus-summary.json',stats)
    proof=p.verify_corpus(source,allowed,corpus);put(RUN/'coverage.json',proof);print('COVERAGE',proof,flush=True)
 elif mode=='embed':
    import numpy as np
    assert read(RUN/'coverage.json')['coverage']==1.0
    model=embedding_model();db=p.connect(corpus);state_path=RUN/'embedding-state.json'
    state=read(state_path) if state_path.exists() else {'status':'embedding','started_at':time.time(),'deadline':time.time()+criteria['resources']['embedding_deadline_seconds'],'corpus_sha256':sha(corpus),'rows':0,'batches':0,'attempts':0}
    assert state['corpus_sha256']==sha(corpus),'Stale embedding state'
    state['attempts']+=1;p.atomic_json(state_path,state)
    n=read(RUN/'corpus-summary.json')['chunks'];size=criteria['resources']['shard_rows']
    for start in range(0,n,size):
        rows=list(db.execute('SELECT id,prefix,text,input_sha256,tokens FROM chunks WHERE id>=? ORDER BY id LIMIT ?',(start,size)))
        assert [r['id'] for r in rows]==list(range(start,start+len(rows)))
        h=p.digest('\n'.join(r['input_sha256'] for r in rows))
        if p.check_shard(RUN/'vectors',start,len(rows),h):continue
        if time.time()>=state['deadline']:raise TimeoutError('Frozen cumulative embedding deadline exhausted')
        texts=[r['prefix']+r['text'] for r in rows]
        lengths=[len(x) for x in model.tokenizer(texts,add_special_tokens=True,truncation=False)['input_ids']]
        assert lengths==[r['tokens'] for r in rows] and max(lengths)<=model.max_seq_length,'implicit tokenizer truncation'
        v=model.encode(texts,normalize_embeddings=True,batch_size=criteria['resources']['batch_size'],show_progress_bar=False)
        p.save_shard(RUN/'vectors',start,v,h)
        state.update(rows=start+len(rows),batches=state['batches']+1,updated_at=time.time());p.atomic_json(state_path,state)
        print('EMBED',state['rows'],'/',n,'elapsed',round(time.time()-state['started_at'],1),'rss_gib',round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,2),flush=True)
    queries=[c['question'] for c in cases]
    assert max(len(x) for x in model.tokenizer(queries,truncation=False)['input_ids'])<=512,'query exceeds fixed embedding limit'
    q=model.encode(queries,normalize_embeddings=True,batch_size=4,show_progress_bar=False);np.save(RUN/'query-vectors.npy',q,allow_pickle=False)
    state.update(status='complete',rows=n,completed_at=time.time());p.atomic_json(state_path,state)
    put(RUN/'vector-manifest.json',{'schema_version':'structured-fulltext-dense-v1','status':'complete','corpus_path':str(corpus.relative_to(ROOT)),'corpus_sha256':sha(corpus),'dimensions':1024,'dtype':'float16','rows':n,'documents':70,'generation_store_sha256':sha(source),'model_lock_sha256':sha(DES/'models.json'),'query_vectors_sha256':sha(RUN/'query-vectors.npy'),'shards':[{'path':str(x.relative_to(ROOT)),**read(x.with_suffix('.json'))} for x in sorted((RUN/'vectors').glob('*.npy'))]})
    db.close()
 elif mode=='retrieve':
    import numpy as np
    manifest=read(RUN/'vector-manifest.json');assert manifest['corpus_sha256']==sha(corpus)
    db=p.connect(corpus);groupkeys=[(r[0],r[1]) for r in db.execute('SELECT doc_id,node FROM groups ORDER BY doc_id,node')];lookup={key:i for i,key in enumerate(groupkeys)}
    queries=np.load(RUN/'query-vectors.npy',allow_pickle=False);scores=np.full((len(cases),len(groupkeys)),-np.inf,dtype='float32');best=np.full(scores.shape,-1,dtype='int64')
    for shard in manifest['shards']:
        assert sha(ROOT/shard['path'])==shard['sha256'];v=np.load(ROOT/shard['path'],mmap_mode='r',allow_pickle=False).astype('float32');v/=np.linalg.norm(v,axis=1,keepdims=True)
        sim=queries@v.T;rows=list(db.execute('SELECT id,doc_id,node FROM chunks WHERE id>=? ORDER BY id LIMIT ?',(shard['start'],shard['rows'])))
        for j,row in enumerate(rows):
            gi=lookup[(row['doc_id'],row['node'])];better=sim[:,j]>scores[:,gi];scores[better,gi]=sim[better,j];best[better,gi]=row['id']
    for i,case in enumerate(cases):
        pool=[]
        for gi in np.argsort(-scores[i],kind='stable')[:50]:
            if not np.isfinite(scores[i,gi]):continue
            doc,node=groupkeys[gi];group=json.loads(db.execute('SELECT json FROM groups WHERE doc_id=? AND node=?',(doc,node)).fetchone()[0])
            chunk=db.execute('SELECT * FROM chunks WHERE id=?',(int(best[i,gi]),)).fetchone()
            pool.append({**group,'chunk_id':chunk['id'],'best_text':chunk['text'],'prefix':chunk['prefix'],'cosine':float(scores[i,gi])})
        gz(RUN/case['id']/'pool.json.gz',pool)
        put(RUN/case['id']/'retrieval.json',{'count':len(pool),'seconds':None,'timing':'shared51-query vector scan; see stage receipt'})
    db.close();print('RETRIEVE51 complete',flush=True)
 elif mode=='rerank':
    import numpy as np
    local_threads()
    from sentence_transformers import CrossEncoder
    model=CrossEncoder(str(ROOT/models['reranker']),device='cpu',max_length=512,local_files_only=True)
    for case in cases:
        tick=time.monotonic();pool=readgz(RUN/case['id']/'pool.json.gz');pairs=[];owners=[];counts=[]
        for i,g in enumerate(pool):
            count=lambda text:len(model.tokenizer(case['question'],text,add_special_tokens=True,truncation=False)['input_ids'])
            prefix=g['prefix'];windows=list(p.split_text(g['best_text'],prefix,count,max_characters=800,max_tokens=512,overlap=100));counts.append(len(windows))
            for a,b in windows:pairs.append((case['question'],prefix+g['best_text'][a:b]));owners.append(i)
        values=model.predict(pairs,batch_size=4,show_progress_bar=False,convert_to_numpy=True);assert np.isfinite(values).all()
        group_scores=np.full(len(pool),-np.inf)
        for i,v in zip(owners,values):group_scores[i]=max(group_scores[i],float(v))
        ranked=[{**pool[int(i)],'rerank_score':float(group_scores[i]),'rerank_windows':counts[i]} for i in np.argsort(-group_scores,kind='stable')]
        gz(RUN/case['id']/'rerank.json.gz',ranked);put(RUN/case['id']/'rerank-timing.json',{'seconds':time.monotonic()-tick,'pairs':len(pairs),'implicit_truncations':0})
        for arm,rank in [('dense',pool),('dense-rerank',ranked)]:gz(RUN/case['id']/(arm+'-context.json.gz'),p.context(source,rank,allowed))
        print('RERANK',case['id'],round(time.monotonic()-tick,1),flush=True)
 elif mode=='answer':
    from lawrag.research.experiment_client import ExperimentClient,ExperimentCallError
    selected=set(criteria['answer_case_ids']);done=[];stop=None
    for i,case in enumerate(cases):
        if case['id'] not in selected:continue
        for arm in (['dense','dense-rerank'] if i%2==0 else ['dense-rerank','dense']):
            if stop:break
            d=RUN/case['id']/arm;d.mkdir();client=ExperimentClient(ROOT,d/'raw',max_calls=1,max_output_tokens=4000,max_repairs=0)
            ctx=readgz(RUN/case['id']/(arm+'-context.json.gz'));tick=time.monotonic();result={'case_id':case['id'],'arm':arm}
            try:
                answer=client.generate(p.ANSWER_SYSTEM,{'question':case['question'],'sources':ctx['sources']},p.ANSWER_SCHEMA,phase='answer')
                put(d/'proposal.json',answer);p.validate_answer(answer,ctx['sources']);result.update(status='complete',answer=answer)
            except (ExperimentCallError,ValueError,KeyboardInterrupt) as exc:
                result.update(status='failed',error_type=type(exc).__name__,error=str(exc));stop={'case_id':case['id'],'arm':arm,'reason':str(exc)}
            result.update(seconds=time.monotonic()-tick,calls=client.calls,usage=client.usage);put(d/'result.json',result);done.append(result)
            print('ANSWER',case['id'],arm,result['status'],flush=True)
        if stop:break
    put(RUN/'answer-summary.json',{'attempted':len(done),'completed':sum(x['status']=='complete' for x in done),'stop':stop,'planned':12,'remaining_not_run':12-len(done)})
 else:raise ValueError(mode)
 put(receipt,{'status':'complete','mode':mode,'seconds':time.monotonic()-started,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'freeze_sha256':sha(DES/'freeze.json')})
 put(attempt_path,{'status':'complete','at':time.time(),'receipt_sha256':sha(receipt)})
except BaseException as exc:
 put(attempt_path,{'status':'partial' if mode=='embed' else 'failed','at':time.time(),'error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'freeze_sha256':sha(DES/'freeze.json')})
 raise
