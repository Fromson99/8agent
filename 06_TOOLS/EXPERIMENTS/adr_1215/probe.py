from common import *
import os,time,resource,types
from jsonschema import Draft202012Validator
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(DES/'freeze.json');C=ROOT/f['code_root']
for p,h in f['files'].items():assert sha(C/p)==h,p
for group in ('inputs','scripts'):
 for p,h in f[group].items():assert sha(ROOT/p)==h,p
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),MALLOC_ARENA_MAX='1')
sys.path.insert(0,str(C/'02_BACKEND'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError
from resource_guard import Guard,self_test
out=ART/'live';out.mkdir(exist_ok=False)
guard=Guard(out);guard.start();assert self_test()==8
client=ExperimentClient(ROOT,out/'calls',max_calls=9,max_repairs=0,schema_in_prompt=False)
def compressed_write(self,path,value):
 path=Path(path)
 if self._key in json.dumps(value,ensure_ascii=False):raise RuntimeError('credential in artifact')
 if path.exists():path=path.with_name(path.stem+'-'+str(self.calls)+'.json')
 raw(path,value)
client._write=types.MethodType(compressed_write,client)
started=time.monotonic();deadline=started+1800;rows=[]
put(out/'dispatch.json',{'started_epoch':time.time(),'maximum_physical_calls':9,'synthetic_only':True})
try:
 for case in read(DES/'requests.json'):
  guard.check();before=client.calls;t=time.monotonic();row={'id':case['id'],'physical_before':before};rows.append(row)
  print('START',case['id'],flush=True)
  try:
   response=client.chat_completions(case['request'],phase=case['id'],timeout_seconds=min(180,deadline-time.monotonic()))
   raw_body=response['body_json'];content=raw_body['choices'][0]['message'].get('content')
   value=json.loads(content);expected=json.loads(case['request']['messages'][1]['content'])
   valid=Draft202012Validator(case['request']['response_format']['json_schema']['schema']).is_valid(value)
   row.update(status='SUCCESS' if valid and value==expected else 'CONTENT_MISMATCH',schema_valid=valid,exact=expected==value)
  except (ExperimentFormatError,ExperimentProviderError) as exc:
   response=exc.response or {};raw_body=response.get('body_json') or {}
   choice=(raw_body.get('choices') or [{}])[0]
   row.update(status=type(exc).__name__,http_status=response.get('status_code'),finish_reason=choice.get('finish_reason'),content_null=(choice.get('message') or {}).get('content') is None)
  except Exception as exc:
   row.update(status='UNKNOWN',error_type=type(exc).__name__)
  row.update(physical_after=client.calls,seconds=time.monotonic()-t)
  put(out/(case['id']+'.json'),row);print(json.dumps(row),flush=True)
  if row['status']=='UNKNOWN':break
finally:
 guard.done.set();guard.thread.join(timeout=2)
 b=read(DES/'baseline.json')
 put(out/'execution.json',{'results':rows,'calls':client.calls,'usage':client.usage,'provider_switches':client.provider_switches,'seconds':time.monotonic()-started,'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256'],'serving_unchanged':all(sha(ROOT/n)==h for n,h in b['release']['files'].items())})
