"""Frozen local-only initial retrieval probe. Gold never read here."""
from pathlib import Path
import os,sys,json,hashlib,sqlite3,time,gzip,socket,threading,signal,resource
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1162-cm-initial-vector-retrieval';D=A/'artifacts/design';O=A/'artifacts/run-001';O.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 with p.open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()
def mem():
 d={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith(('MemAvailable:','SwapTotal:','SwapFree:'))};d['rss']=next(int(x.split()[1])*1024 for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:'));d['swap_used']=d['SwapTotal']-d['SwapFree'];return d
assert not (O/'rankings.json').exists();started=time.monotonic();initial=mem();assert initial['MemAvailable']>=3*1024**3,'insufficient memory before encoder probe'
phase='verify';alive=True
put(O/'start.json',{'pid':os.getpid(),'memory':initial,'started_at':time.time(),'external_calls':0,'generation_calls':0})
def watch():
 while alive:
  m=mem()
  if m['rss']>3.5*1024**3 or m['MemAvailable']<.8*1024**3 or m['swap_used']-initial['swap_used']>384*1024**2 or time.monotonic()-started>600:
   put(O/'resource-stop.json',{'phase':phase,'memory':m,'initial':initial,'elapsed':time.monotonic()-started,'external_calls':0});os._exit(124)
  time.sleep(1)
threading.Thread(target=watch,daemon=True).start()
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',HF_HOME='/home/jin/.cache/huggingface')
original_connect=socket.socket.connect
def no_tcp(self,address):
 if self.family in (socket.AF_INET,socket.AF_INET6):raise RuntimeError('network prohibited for local vector experiment')
 return original_connect(self,address)
socket.socket.connect=no_tcp
f=read(D/'freeze.json')
for p,h in f['inputs'].items():assert sha(R/p)==h,p
model=read(D/'model.json')
for n,h in model['files'].items():assert sha(Path(model['path'])/n)==h['sha256'],n
import numpy as np
scope=set(read(D/'corpus.json')['document_ids']);data=R/f['data_path'];db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True);nav=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
marks=','.join('?' for _ in scope);units={(d,str(u)):(str(p) if p is not None else None,json.loads(j)) for d,u,p,j in db.execute('SELECT document_id,unit_id,parent_id,json FROM source_unit WHERE document_id IN ('+marks+')',list(scope))};texts={(d,str(b)):t for d,b,t in db.execute('SELECT document_id,block_id,text FROM source_block WHERE document_id IN ('+marks+')',list(scope))};db.close()
sources={};rootnames={};unitroots={}
for sid,did,raw in nav.execute('SELECT id,document_id,json FROM source WHERE document_id IN ('+marks+')',list(scope)):
 x=json.loads(raw);c=x.get('article_coordinate') or {};coord=(c.get('doc_id',did),int(c.get('node',x['unit_id'])));sources[sid]=coord;unitroots[(did,str(x['unit_id']))]=coord;rootnames[coord]={'document':x.get('document_name'),'article':x.get('heading')}
nav.close()
def root(k):
 seen=set()
 while k in units and k not in seen:
  if k in unitroots:return unitroots[k]
  seen.add(k);parent=units[k][0];k=(k[0],parent)
 return None
meta=[json.loads(t) for t in (R/'01_DATA/embeddings/sections/meta.jsonl').read_text().splitlines()];keep=[];mapping=[];encoded=[];reasons={};phase='cache_match'
for i,m in enumerate(meta):
 k=(m['doc_id'],str(m['node']))
 if k[0] not in scope:continue
 if k not in units:reasons['missing_unit']=reasons.get('missing_unit',0)+1;continue
 unit=units[k][1];start,end=unit['span'];parts=[];size=0;cut=False
 for n in range(start,max(end,start+1)):
  text=texts.get((k[0],str(n)),'').strip()
  if text:parts.append(text);size+=len(text)
  if size>=800:cut=n+1<end;break
 body='\n'.join(parts)
 if len(body)>800:body=body[:800];cut=True
 if cut:body+='\n…(구역이 길어 여기서 잘림 — 이후 내용 있음)'
 labels=[];cur=k;seen=set()
 while cur in units and cur not in seen:
  seen.add(cur);parent,u=units[cur];sf=u.get('surface','').strip();title=u.get('title','').strip();label=f'{sf} {title}' if sf and title and sf not in title else title or sf
  if label:labels.append(label)
  cur=(k[0],parent) if parent is not None else None
 text=(' ▸ '.join(reversed(labels))+'\n'+body).strip();coord=root(k)
 if hashlib.sha1(text.encode()).hexdigest()[:16]!=m['sha1']:reasons['input_hash_mismatch']=reasons.get('input_hash_mismatch',0)+1;continue
 if coord is None:reasons['no_article_root']=reasons.get('no_article_root',0)+1;continue
 keep.append(i);mapping.append(coord);encoded.append(text)
assert keep,'no verified reusable vectors'
with np.load(R/'01_DATA/embeddings/sections/vectors.npz',allow_pickle=False) as old:v=old['v'][keep].astype(np.float16)
assert len(meta)>max(keep);sample_ids=sorted({0,len(keep)//2,len(keep)-1});sampletexts=[encoded[i] for i in sample_ids]
covered=set(mapping);corpus=set(rootnames);put(O/'coverage.json',{'original_corpus_roots':len(corpus),'covered_roots':len(covered),'covered_docs':len({d for d,n in covered}),'authorized_docs':len(scope),'matched_sections':len(keep),'rejected':reasons,'cache_rows':len(meta),'sample_indices':sample_ids,'source_input_hash_match':True,'covered_coordinates':[{'doc_id':d,'node':n} for d,n in sorted(covered)]})
print('CACHE',len(keep),'sections',len(covered),'/',len(corpus),'roots',flush=True)
del units,texts,meta,encoded;import gc;gc.collect();phase='encoder_load';loadstart=time.monotonic()
import torch
torch.set_num_threads(2)
from sentence_transformers import SentenceTransformer
encoder=SentenceTransformer(model['path'],device='cpu',local_files_only=True,model_kwargs={'torch_dtype':torch.float16,'low_cpu_mem_usage':True});loadseconds=time.monotonic()-loadstart
phase='encoder_check';fresh=encoder.encode(sampletexts,batch_size=1,normalize_embeddings=True,show_progress_bar=False);old=v[sample_ids].astype(np.float32);old/=np.maximum(np.linalg.norm(old,axis=1,keepdims=True),1e-12);cos=np.sum(fresh.astype(np.float32)*old,axis=1);put(O/'encoder-check.json',{'cosines':cos.tolist(),'threshold':.995,'pass':bool(cos.min()>=.995),'load_seconds':loadseconds,'dtype':str(next(encoder.parameters()).dtype),'local_samples':len(sampletexts)});assert cos.min()>=.995,'cache encoder incompatible'
phase='queries';saved=read(D/'saved-keyword.json');cases=read(D/'cases.json');rows=[];ft=sqlite3.connect((data/'fulltext/units.sqlite').as_uri()+'?mode=ro',uri=True)
from semantic_runtime.fulltext import _search_forms,expression
for case in cases:
 cid=case['id'];question=case['request']['json']['question'];qstart=time.monotonic();q=encoder.encode([question],batch_size=1,normalize_embeddings=True,show_progress_bar=False)[0].astype(np.float32);encseconds=time.monotonic()-qstart;rankstart=time.monotonic();best={};sections={}
 for off in range(0,len(v),4096):
  block=v[off:off+4096].astype(np.float32);block/=np.maximum(np.linalg.norm(block,axis=1,keepdims=True),1e-12);scores=block@q
  for j,score in enumerate(scores):
   coord=mapping[off+j];score=float(score)
   if coord not in best or score>best[coord]:best[coord]=score;sections[coord]=keep[off+j]
 vr=sorted(best,key=lambda c:(-best[c],c));dense_seconds=time.monotonic()-rankstart
 terms=sorted({t for q0 in saved[cid]['queries'] for t in _search_forms(q0)});ls=time.monotonic();matches=ft.execute('SELECT u.source_id,unit_fts.rank FROM unit_fts JOIN unit u ON u.key=unit_fts.key WHERE unit_fts MATCH ? AND u.source_id IN (SELECT value FROM json_each(?))',(expression(terms),json.dumps(sorted(sources)))).fetchall();lex={}
 for sid,score in matches:
  coord=sources[sid];lex[coord]=min(score,lex.get(coord,float('inf')))
 lr=sorted(lex,key=lambda c:(lex[c],c));lexseconds=time.monotonic()-ls;rrf={}
 for ranking in [lr,vr]:
  for rank,coord in enumerate(ranking,1):rrf[coord]=rrf.get(coord,0)+1/(60+rank)
 hr=sorted(rrf,key=lambda c:(-rrf[c],c));sr=list(dict.fromkeys((x['doc_id'],x['node']) for x in saved[cid]['visible_article_roots']))
 def records(coords,scores=None):return [{'doc_id':d,'node':n,**rootnames[(d,n)],**({'score':scores[(d,n)]} if scores is not None else {})} for d,n in coords]
 pools={'saved_keyword':sr,'lexical_global':lr,'vector':vr,'hybrid':hr};row={'case':cid,'question':question,'lexical_queries':saved[cid]['queries'],'terms':terms,'timing':{'query_encode_seconds':encseconds,'dense_rank_seconds':dense_seconds,'lexical_rank_seconds':lexseconds},'rankings':{a:records(xs,{'vector':best,'hybrid':rrf,'lexical_global':lex}.get(a)) for a,xs in pools.items()},'lexical_covered_ranking':records([c for c in lr if c in covered],lex)};rows.append(row);put(O/(cid+'-rankings.json'),row);print('RANKED',cid,'encode',round(encseconds,3),'dense',round(dense_seconds,3),'lexical',round(lexseconds,3),flush=True)
ft.close();phase='complete';put(O/'rankings.json',{'status':'complete','cases':rows,'setup_seconds':loadseconds,'total_seconds':time.monotonic()-started,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'external_calls':0,'generation_calls':0,'local_encoder_inputs':6,'model':'BAAI/bge-m3','network_blocked':True,'gold_read_by_ranker':False,'active_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']});alive=False;print('COMPLETE no external calls',flush=True)
