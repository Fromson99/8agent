from common import *
import sqlite3,time,types,httpx,traceback,resource
from unittest.mock import patch
os.environ.update(MALLOC_ARENA_MAX='1',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT))
os.environ.pop('DP',None)
case=sys.argv[1];assert case in ('corroborate','conflict')
preflight='--preflight' in sys.argv
out=ART/(('ready-final-' if preflight else 'followup-')+case);out.mkdir(exist_ok=False)
C=ROOT/read(DES/'candidate.json')['code_root']
from pinned_imports import install
install(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for pkg,path in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:pkg.__path__.extend([str(C/path),str(ROOT/path)])
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from semantic_runtime.ontology_work.repository import Repository
from semantic_runtime.ontology_work.store import LocalFolderStore
from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
from semantic_runtime.ontology_work.wiki_workspace import Workspace
from semantic_runtime.ontology_work.wiki_projection import compare_judgment
from semantic_runtime.ontology_work import wiki_contracts as wc,authoring_model
from semantic_runtime.ontology_work.configuration import source_reader
from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
from semantic_runtime.ontology_work.observations import envelope
from semantic_runtime.full_glossary import Glossary
from semantic_runtime.full_glossary_connections import ConnectionReader
from semantic_runtime.contracts import digest
from semantic_runtime import genos
from lawrag.core import request_deadline as dt
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError
from resource_guard import Guard
guard=Guard(out);guard.start()
b=read(DES/'baseline.json');data=ROOT/b['release']['data_path'];meta=read(data/'manifest.json');g=meta['glossary']
reader=Glossary(data/g['bundle'],data/g['dictionary'],data/g['cache'],manifest_sha256=g['manifest_sha256'],connection_factory=ConnectionReader)
glossary=GlossaryBinding(reader,snapshot=meta['generation_id'])
base_dir = ART/('preflight-repository' if preflight else 'sandbox-repository')
repo=Repository(lambda:sqlite3.connect(base_dir/'work.sqlite'));store=LocalFolderStore(base_dir/'objects')
documents=read(DES/'source-scope.json')['public']
source=source_reader({'environment':'local','source':{'kind':'sqlite-local','path':str(data/'store.sqlite')}},documents)
args=dict(actor='codex-isolated-experiment-reviewer',source_reader=source,generate=None,namespace='ADR1371-only',source_snapshot=meta['generation_id'],acl_ref=digest(documents),document_ids=documents,glossary=glossary,producer_binding=read(DES/'candidate.json')['pin']['revision_sha256'])
w=Workspace(repo,store,can_publish=True,**args)
repo.workspace_scopes={wc.scope_key(w.scope())}
parent=read(DES/'parent-knowledge.json')
target=read(DES/'followups.json')[case];origin=read(ROOT/target['path'])
for key in target['pointer']:origin=origin[key]
assert origin==target['payload'] and sha(ROOT/target['path'])==target['sha256']
record=envelope(origin,namespace=w.namespace,run_id=target['run_id'],event_id=target['path']+str(target['pointer']),sequence=0,source_snapshot=w.source_snapshot,producer_binding=target['sha256'],acl_ref=w.acl_ref,document_ids=documents,format_description='Exact earlier public Qwen statement, possible error; independently verify original text',origin='ARCHIVED_MODEL_OUTPUT')
r=w.ingest(record);assert w.ingest(record)['work_hash']==r['work_hash']
previous=w.load(parent['bundle_id']);assert previous['revision']==(1 if case=='corroborate' or preflight else 2)
client=None;calls=[];logical=[];phase='WIKI_PROPOSE';started=time.monotonic();endpoint=types.SimpleNamespace(headers={},url=lambda path:'https://authoring-experiment.invalid'+path)
original_post=dt.post_json
def raw(p,v):
 ref=write_raw_json(p,v);put(str(p)+'.ref.json',ref)
def observed_post(url,**kw):
 if url.startswith('https://authoring-experiment.invalid/'):
  if preflight:return httpx.Response(429,json={'error':'Synthetic admission boundary, no physical call'})
  try:
   response=client.chat_completions(kw['json_body'],phase=phase,timeout_seconds=min(180,max(1,kw['deadline']-time.monotonic())))
  except ExperimentFormatError as exc:raise authoring_model.AuthoringFailure('INCOMPLETE_RESPONSE',{'response':exc.response,'physical_calls':1}) from exc
  except ExperimentProviderError as exc:raise authoring_model.AuthoringFailure('HTTP_REJECTED',{'response':exc.response,'physical_calls':1}) from exc
  return httpx.Response(response['status_code'],json=response['body_json'])
 guard.check()
 if (ART/'STOP_EXTERNAL.json').exists():raise RuntimeError('Unknown outcome prevents new sends')
 n=len(calls)+1;d=out/'raw'/f'call-{n:03d}';d.mkdir(parents=True,exist_ok=False)
 payload=kw['json_body'];assert payload['model']=='qwen/qwen3.8-27b' and payload['reasoning']=={'effort':'none'}
 assert not {'max_tokens','max_completion_tokens','max_output_tokens'}&payload.keys()
 raw(d/'request.json.gz',payload);row={'number':n,'stage':phase,'status':'started'};calls.append(row);put(out/'calls.json',calls);t=time.monotonic()
 print('BUILD_MODEL',n,phase,flush=True)
 try:
  response=original_post(url,**kw)
  try:v=response.json()
  except ValueError:v={'non_json_body':response.text}
  raw(d/'response.json.gz',v);row.update(status='responded',http_status=response.status_code,usage=v.get('usage'),actual_provider=v.get('provider'),actual_model=v.get('model'))
  return response
 except Exception as exc:
  row.update(status='unknown',error_type=type(exc).__name__,diagnostics=getattr(exc,'diagnostics',{}))
  if hasattr(exc,'partial_body'):
   import base64
   raw(d/'partial.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode()})
  put(ART/'STOP_EXTERNAL.json',{'stage':'BUILD','call':n,'reason':'UNKNOWN physical outcome','no_resend':True});raise
 finally:row['seconds']=time.monotonic()-t;put(out/'calls.json',calls);put(d/'finished.json',row)
def generate(prompt,context,schema):
 global phase
 phase=context.get('operation', 'NORMALIZE' if 'raw' in context else 'WIKI_PROJECT' if 'statements' in context else 'WIKI_PROPOSE')
 before=len(calls);n=len(logical)+1;row={'number':n,'stage':phase};logical.append(row)
 raw(out/'canonical'/f'{n:03d}.json.gz',{'prompt':prompt,'context':context,'schema':schema})
 try:
  with patch.object(genos,'from_env',lambda kind:(endpoint,'qwen/qwen3.8-27b')),patch.object(genos,'advertised_model',lambda *a:'qwen/qwen3.8-27b'):
   value,receipt=authoring_model.generate(store,prompt,context,schema)
  raw(out/'canonical'/f'{n:03d}-output.json.gz',value);row['status']='RECEIVED'
  return value,{**receipt,'physical_calls':len(calls)-before}
 except Exception as exc:row.update(status='FAILED',error_type=type(exc).__name__,error=str(exc));raise
 finally:put(out/'generations.json',logical)
result={'status':'STARTED','knowledge_approved':False,'published':False}
try:
 if not preflight:
  for n,h in read(DES/'freeze.json')['files'].items():assert sha(ROOT/n)==h,n
  assert read(ART/'ready-final-corroborate/result.json')['ready']
  client=ExperimentClient(ROOT,out/'experiment-client',max_calls=11,max_repairs=0,schema_in_prompt=False,provider_policy=DES/'provider-policy.json')
  from observer import install as install_observer
  install_observer(client)
 w.generate=generate
 with patch.object(dt,'post_json',observed_post):
  request={'bundle_id':parent['bundle_id'],'revision':previous['revision'],'work_hash':previous['work_hash'],'raw_id':r['bundle_id']}
  saved=compare_judgment(w,w,**request);after=w.load(parent['bundle_id']);before_calls=len(calls)
  assert compare_judgment(w,w,**request)['reused'] and len(calls)==before_calls
  assert after['base_work_hash']==previous['work_hash'] and after['revision']==previous['revision']+1
  assert after['proposal']['graph']==previous['proposal']['graph'] and after['workspace_projection']==previous['workspace_projection']
  assert after['comparison_history'][:-1]==previous['comparison_history'] and all(after['observation_ledger'][k]==v for k,v in previous['observation_ledger'].items())
  raw(out/'document.json.gz',after)
  put(out/'compared.json',{'request':request,'record':r,'new_comparisons':after['proposal']['comparisons'],'observation_count_before':len(previous['observation_ledger']),'observation_count_after':len(after['observation_ledger']),'same_graph':True,'same_projection':True,'prior_evidence_retained':True,'duplicate_extra_calls':0})
  result.update(status='SAVED',row=saved,review_state=after['review_state'],history=len(after['comparison_history']),same_graph=True)
except Exception as exc:
 result.update(status='ADMISSION_COMPLETE' if preflight and isinstance(exc,authoring_model.AuthoringFailure) and exc.status=='HTTP_REJECTED' else 'FAILED',stage=phase,error_type=type(exc).__name__,error=str(exc))
 result['ready']=result['status']=='ADMISSION_COMPLETE';(out/'error.txt').write_text(traceback.format_exc())
finally:
 result.update(physical_calls=len(calls),unknown=sum(x['status']=='unknown' for x in calls),seconds=time.monotonic()-started,reported_cost_usd=sum((x.get('usage') or {}).get('cost',0) for x in calls),reported_tokens=sum((x.get('usage') or {}).get('total_tokens',0) for x in calls),peak_rss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
 put(out/'result.json',result);guard.done.set();guard.thread.join(timeout=2);reader.close();print(json.dumps(result,ensure_ascii=False),flush=True)
