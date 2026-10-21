"""Serial stages with exact pins. Never reads reference answers or targets."""
from common import *
import sys,os,time,importlib.util,gzip,resource
sys.dont_write_bytecode=True
mode=sys.argv[1];f=read(DES/'freeze.json');criteria=read(DES/'criteria.json');models=read(DES/'models.json')
for p,h in f['files'].items():assert sha(ROOT/p)==h,'Frozen input changed: '+p
for p,h in models['files'].items():assert sha(ROOT/p)==h,'Model bytes changed: '+p
c=f['candidates'][1];cp=ROOT/c['manifest_path'];assert sha(cp)==c['manifest_sha256']
revision=cp.parent/'revisions'/c['revision_id']/'snapshot'
for arm in f['candidates']:
    cm=read(ROOT/arm['manifest_path'])
    for row in cm['revisions'][-1]['files']:
        assert sha(ROOT/row['frozen_path'])==row['snapshot_sha256'],'Frozen candidate changed'
candidate=revision/TARGET
spec=importlib.util.spec_from_file_location('dense_probe',candidate);p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
cases=read(DES/'cases.json');allowed=set(criteria['scope']);source=ROOT/criteria['generation_path']/'store.sqlite'
RUN.mkdir(parents=True,exist_ok=True)
out=RUN/(mode+'-receipt.json');assert not out.exists(),'Do not rerun completed stage'
if (RUN/(mode+'-started.json')).exists():raise RuntimeError('Stage previously started; preserve partial results and investigate before rerun')
put(RUN/(mode+'-started.json'),{'time':time.time(),'mode':mode,'freeze_sha256':sha(DES/'freeze.json')})
started=time.monotonic()
if mode=='corpus':
    corpus=p.build_corpus(source,ROOT/'01_DATA/embeddings/sections/meta.jsonl',allowed,RUN/'corpus.jsonl.gz')
    put(RUN/'corpus-summary.json',corpus);print(corpus['counts'],flush=True)
elif mode=='embed':
    import numpy as np,torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    from sentence_transformers import SentenceTransformer
    with gzip.open(RUN/'corpus.jsonl.gz','rt',encoding='utf8') as fi:rows=[json.loads(x) for x in fi]
    with np.load(ROOT/'01_DATA/embeddings/sections/vectors.npz',allow_pickle=False) as z:v=z['v']
    sample=np.linspace(0,len(rows)-1,16,dtype=int);ids=[rows[i]['row'] for i in sample]
    old=v[ids].astype('float32');old/=np.linalg.norm(old,axis=1,keepdims=True);del v
    model=SentenceTransformer(str(ROOT/models['embedding']),device='cpu',local_files_only=True,model_kwargs={'use_safetensors':True})
    new=model.encode([rows[i]['text'] for i in sample],normalize_embeddings=True,batch_size=2,show_progress_bar=False)
    cos=np.sum(new*old,axis=1);put(RUN/'embedding-compatibility.json',{'cosines':cos.tolist(),'sample_rows':ids,'threshold':0.995,'pass':bool(cos.min()>=.995)})
    assert cos.min()>=.995,'Legacy embedding model mismatch'
    queries=model.encode([x['question'] for x in cases],normalize_embeddings=True,batch_size=2,show_progress_bar=False)
    np.save(RUN/'query-vectors.npy',queries)
    print('Encoded51 exact questions; cache sample min cosine',float(cos.min()),flush=True)
elif mode=='retrieve':
    import numpy as np
    with gzip.open(RUN/'corpus.jsonl.gz','rt',encoding='utf8') as fi:rows=[json.loads(x) for x in fi]
    with np.load(ROOT/'01_DATA/embeddings/sections/vectors.npz',allow_pickle=False) as z:old=z['v'];v=old[[r['row'] for r in rows]].astype('float32')
    del old;v/=np.maximum(np.linalg.norm(v,axis=1,keepdims=True),1e-12);q=np.load(RUN/'query-vectors.npy')
    for case,query in zip(cases,q):
        tick=time.monotonic();pool=p.rank_articles(rows,v,query)
        gz(RUN/case['id']/'pool.json.gz',pool);put(RUN/case['id']/'retrieval.json',{'seconds':time.monotonic()-tick,'count':len(pool)})
    print('Retrieved51 dense top50 pools',flush=True)
elif mode=='rerank':
    import torch
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    from sentence_transformers import CrossEncoder
    model=CrossEncoder(str(ROOT/models['reranker']),device='cpu',max_length=512,local_files_only=True)
    for case in cases:
        tick=time.monotonic();pool=readgz(RUN/case['id']/'pool.json.gz');ranked=p.rerank(case['question'],pool,model)
        gz(RUN/case['id']/'rerank.json.gz',ranked);put(RUN/case['id']/'rerank-timing.json',{'seconds':time.monotonic()-tick,'pairs':len(pool)})
        for arm,r in [('dense',pool),('dense-rerank',ranked)]:gz(RUN/case['id']/(arm+'-context.json.gz'),p.context(source,r,allowed))
        print('RERANK',case['id'],round(time.monotonic()-tick,1),flush=True)
elif mode=='answer':
    sys.path.insert(0,str(ROOT/'02_BACKEND'))
    from lawrag.research.experiment_client import ExperimentClient,ExperimentCallError
    stop=None;done=[];selected=set(criteria['answer_case_ids'])
    for i,case in enumerate(cases):
        if case['id'] not in selected:continue
        for arm in (['dense','dense-rerank'] if i%2==0 else ['dense-rerank','dense']):
            if stop:break
            directory=RUN/case['id']/arm;assert not directory.exists();directory.mkdir()
            client=ExperimentClient(ROOT,directory/'raw',max_calls=1,max_output_tokens=4000,max_repairs=0)
            context=readgz(RUN/case['id']/(arm+'-context.json.gz'));tick=time.monotonic()
            result={'case_id':case['id'],'arm':arm,'status':'started'}
            try:
                answer=client.generate(p.ANSWER_SYSTEM,{'question':case['question'],'sources':context['sources']},p.ANSWER_SCHEMA,phase='answer')
                put(directory/'proposal.json',answer);p.validate_answer(answer,context['sources']);result.update(status='complete',answer=answer)
            except (ExperimentCallError,ValueError,KeyboardInterrupt) as exc:
                result.update(status='failed',error_type=type(exc).__name__,error=str(exc))
                # Break the whole external batch on rejection; do not spend calls on known unavailability.
                stop={'case_id':case['id'],'arm':arm,'reason':type(exc).__name__+': '+str(exc)}
            result.update(seconds=time.monotonic()-tick,calls=client.calls,usage=client.usage);put(directory/'result.json',result);done.append(result)
            print('ANSWER',case['id'],arm,result['status'],flush=True)
        if stop:break
    put(RUN/'answer-summary.json',{'attempted':len(done),'completed':sum(x['status']=='complete' for x in done),'stop':stop,'planned':12,'remaining_not_run':12-len(done)})
else:raise ValueError(mode)
put(out,{'mode':mode,'status':'complete','seconds':time.monotonic()-started,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'freeze_sha256':sha(DES/'freeze.json')})
