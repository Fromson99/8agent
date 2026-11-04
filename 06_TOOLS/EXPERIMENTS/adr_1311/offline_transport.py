from common import *
from copy import deepcopy
import socket,re
class ReplayBoundary(RuntimeError):pass
def deny_network():
 for name in ('connect','connect_ex','sendto'):
  old=getattr(socket.socket,name)
  def wrapped(sock,*a,_old=old,**k):
   if sock.family in (socket.AF_INET,socket.AF_INET6):raise ReplayBoundary('Offline profile forbids network')
   return _old(sock,*a,**k)
  setattr(socket.socket,name,wrapped)
 def denied(*a,**k):raise ReplayBoundary('Offline profile forbids DNS')
 socket.getaddrinfo=denied

def comparable(value):
 result=deepcopy(value)
 result.pop('usage',None) # ExperimentClient alone adds usage reporting, after native send_once.
 for msg in result.get('messages',[]):
  if msg['role']!='user':continue
  try:u=json.loads(msg['content'])
  except (TypeError,ValueError):continue
  v=u.get('view',{})
  if re.fullmatch(r'V[0-9a-f]{32}',str(v.get('view_id',''))):v.pop('view_id')
  msg['content']=u
 return result

def differences(a,b,path=''):
 if type(a)!=type(b):return [path+' TYPE']
 if isinstance(a,dict):
  return [p for k in sorted(set(a)|set(b)) for p in ([path+'/'+k+' MISSING'] if k not in a or k not in b else differences(a[k],b[k],path+'/'+k))]
 if isinstance(a,list):
  if len(a)!=len(b):return [path+' LENGTH']
  return [p for i,(x,y) in enumerate(zip(a,b)) for p in differences(x,y,path+'/'+str(i))]
 return [] if a==b else [path]
class Tape:
 def __init__(self,source,out):self.source=source;self.out=out;self.n=0;self.checks=[]
 def reply(self,body):
  from semantic_runtime.legal_agent.local_gemma import provider_request
  n=self.n+1
  if n>8:raise ReplayBoundary('Recorded response tape exhausted')
  expected=read(self.source/'raw'/f'call-{n:03d}'/'request.json.gz');actual=provider_request(body)
  aa,bb=comparable(expected),comparable(actual);diff=differences(aa,bb)
  check={'call':n,'protected_exact':not diff,'differences':diff,'response_rewritten':False,'physical_calls':0};self.checks.append(check);put(self.out/'replay-checks.json',self.checks)
  if diff:
   write_raw_json(self.out/'mismatch-expected.json.gz',aa);write_raw_json(self.out/'mismatch-actual.json.gz',bb)
   raise ReplayBoundary('Protected input differs '+str(diff[:8]))
  raw=read(self.source/'raw'/f'call-{n:03d}'/'response.json.gz')
  assert raw['provider']=='Near AI' and raw['model']=='qwen/qwen3.8-27b' and raw['choices'][0]['finish_reason']=='stop'
  self.n=n;print('REPLAY_RESPONSE',n,flush=True)
  return {'status_code':200,'body_json':raw}
 def complete(self,body):
  expected=read(self.source/'response.json.gz')['body']
  # Run/query IDs are journal-bound UUIDs; final content/claims/source IDs remain exact.
  for k in ('text','claims','scope','generation_id','source_store_sha256','unresolved'):
   if body['answer'].get(k)!=expected['answer'].get(k):raise ReplayBoundary('Final answer differs: '+k)
  assert self.n==8
  return True
