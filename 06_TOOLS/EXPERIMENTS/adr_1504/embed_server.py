"""Local BAAI/bge-m3 embedding endpoint for the experiment (OpenAI-style /v1/embeddings).

The Gold vector publication (A8_GR12_CM1208.IDD_B03_LGL_VCTR_POST) was embedded with
BAAI/bge-m3, 1024 dimensions, l2-normalised, COSINE. The serving code only knows an HTTP
embedding endpoint (semantic_runtime.oracle_query_vector.PublishedEncoder), so this process
serves the same model from the local Hugging Face cache. Every model file is checked against
the hashes recorded in the publication profile before serving. No product code is changed.

usage: embed_server.py --port 8765 --profile-files FILES.json --log DIR [--validate ITEMS.json]
"""
from pathlib import Path
import argparse,hashlib,json,os,sys,time,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

HUB=Path.home()/'.cache/huggingface/hub/models--BAAI--bge-m3'
CONFIG_SNAPSHOT=HUB/'snapshots/5617a9f61b028005a4858fdac845db406aefb181'
WEIGHT_BLOB=HUB/'blobs/993b2248881724788dcab8c644a91dfd63584b6e5604ff2037cb5541e1e38e7e'

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def build_model_dir(target,expected):
 """Assemble the exact published file set from the local cache (symlinks), verifying every hash."""
 target=Path(target);target.mkdir(parents=True,exist_ok=True)
 report={}
 for relative,digest in expected.items():
  dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True)
  source=WEIGHT_BLOB if relative=='model.safetensors' else CONFIG_SNAPSHOT/relative
  if not source.exists():raise FileNotFoundError(str(source))
  if dest.is_symlink() or dest.exists():dest.unlink()
  dest.symlink_to(source.resolve())
  got=sha(dest)
  if got!=digest:raise RuntimeError('MODEL_FILE_HASH:'+relative+':'+got)
  report[relative]=got
 return report

class Encoder:
 def __init__(self,model_dir):
  import torch
  torch.set_num_threads(int(os.environ.get('EMBED_THREADS','4')))
  from sentence_transformers import SentenceTransformer
  self.model=SentenceTransformer(str(model_dir),device='cpu',local_files_only=True)
  self.lock=threading.Lock();self.calls=0
 def encode(self,texts):
  with self.lock:
   self.calls+=1
   vectors=self.model.encode(list(texts),normalize_embeddings=True,show_progress_bar=False,batch_size=8)
  return [[float(x) for x in v] for v in vectors]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8765);ap.add_argument('--profile-files',required=True)
 ap.add_argument('--log',required=True);ap.add_argument('--validate');ap.add_argument('--model-dir',default=None);a=ap.parse_args()
 log=Path(a.log);log.mkdir(parents=True,exist_ok=True)
 expected=json.loads(Path(a.profile_files).read_text())
 model_dir=Path(a.model_dir) if a.model_dir else log/'model'
 files=build_model_dir(model_dir,expected)
 started=time.time();encoder=Encoder(model_dir);load_seconds=time.time()-started
 status={'model':'BAAI/bge-m3','files':files,'load_seconds':load_seconds,'dimensions':len(encoder.encode(['차원 확인'])[0]),'pid':os.getpid(),'port':a.port}
 if a.validate:
  import math
  rows=json.loads(Path(a.validate).read_text());checks=[]
  for row in rows:
   got=encoder.encode([row['input']])[0];stored=row['vector']
   cos=sum(x*y for x,y in zip(got,stored))/(math.sqrt(sum(x*x for x in got))*math.sqrt(sum(y*y for y in stored)))
   checks.append({'unit':row.get('unit'),'cosine':cos})
  status['validation']={'rows':checks,'min_cosine':min(c['cosine'] for c in checks) if checks else None}
 (log/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=1))
 calls=(log/'calls.jsonl').open('a')
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def _send(self,code,value):
   body=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def do_GET(self):
   self._send(200,{'status':'ok','calls':encoder.calls} if self.path.rstrip('/').endswith('health') else {'error':'not found'})
  def do_POST(self):
   if not self.path.rstrip('/').endswith('/embeddings'):return self._send(404,{'error':'not found'})
   n=int(self.headers.get('Content-Length','0'));payload=json.loads(self.rfile.read(n) or b'{}')
   texts=payload.get('input');texts=[texts] if isinstance(texts,str) else list(texts or [])
   if not texts or len(texts)>16 or any(not isinstance(t,str) or not t.strip() for t in texts):return self._send(400,{'error':'bounded nonempty input required'})
   begin=time.time();vectors=encoder.encode(texts);seconds=time.time()-begin
   calls.write(json.dumps({'time':begin,'seconds':seconds,'inputs':len(texts),'chars':[len(t) for t in texts],'model':payload.get('model'),'auth':bool(self.headers.get('Authorization'))})+'\n');calls.flush()
   self._send(200,{'object':'list','model':'BAAI/bge-m3','data':[{'object':'embedding','index':i,'embedding':v} for i,v in enumerate(vectors)],'usage':{'prompt_tokens':0,'total_tokens':0}})
 server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
 print('EMBED_SERVER_READY',a.port,json.dumps({k:status[k] for k in ('load_seconds','dimensions')}),flush=True)
 server.serve_forever()

if __name__=='__main__':main()
