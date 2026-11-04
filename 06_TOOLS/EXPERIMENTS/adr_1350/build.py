from common import *
import sqlite3,time,types,httpx,traceback,resource
from unittest.mock import patch
os.environ.update(MALLOC_ARENA_MAX='1',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT))
os.environ.pop('DP',None)
preflight='--preflight' in sys.argv
out=ART/('build-ready' if preflight else 'build-live');out.mkdir(exist_ok=False)
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
from semantic_runtime.ontology_work.wiki_projection import compile_selection
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
repo=Repository(lambda:sqlite3.connect(out/'work.sqlite'));repo.initialize();store=LocalFolderStore(out/'objects')
documents=read(DES/'source-scope.json')['public'];sources=read(DES/'originals.json')
source=source_reader({'environment':'local','source':{'kind':'sqlite-local','path':str(data/'store.sqlite')}},documents)
for s in sources:assert source(s['anchor'])==s['text']
args=dict(actor='codex-isolated-experiment-reviewer',source_reader=source,generate=None,namespace='ADR1350-only',source_snapshot=meta['generation_id'],acl_ref=digest(documents),document_ids=documents,glossary=glossary,producer_binding=read(DES/'candidate.json')['pin']['revision_sha256'])
w=Workspace(repo,store,can_publish=True,**args);domain=DomainWorkflow(repo,store,**args);domain.can_publish_workspace=True
repo.workspace_scopes={wc.scope_key(w.scope())}
p=domain.save_profile(read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'),read(C/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'))
domain.review_profile(p['bundle_id'],p['revision'],p['work_hash'],True,'Existing profile admitted for isolated test, not legal knowledge approval')
c=read(DES/'records.json')[0];origin=read(ROOT/c['origin']['path'])
for k in c['origin']['pointer'].strip('/').split('/'):origin=origin[int(k)] if isinstance(origin,list) else origin[k]
assert origin==c['payload'] and sha(ROOT/c['origin']['path'])==c['origin']['sha256']
record=envelope(origin,namespace=w.namespace,run_id=c['id'],event_id=c['origin']['path']+c['origin']['pointer'],sequence=0,source_snapshot=w.source_snapshot,producer_binding=c['origin']['sha256'],acl_ref=w.acl_ref,document_ids=documents,format_description='Exact archived investigation judgment, not answer key',origin='ARCHIVED_MODEL_OUTPUT')
r=w.ingest(record);assert w.ingest(record)['work_hash']==r['work_hash']
put(out/'binding.json',{'profile':p,'raw':r,'scope':w.scope(),'workspace_scopes':list(repo.workspace_scopes),'code':str(C),'originals':len(sources),'glossary':glossary.binding})
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
 n=len(logical)+1;row={'number':n,'stage':phase};logical.append(row)
 raw(out/'canonical'/f'{n:03d}.json.gz',{'prompt':prompt,'context':context,'schema':schema})
 try:
  with patch.object(genos,'from_env',lambda kind:(endpoint,'qwen/qwen3.8-27b')),patch.object(genos,'advertised_model',lambda *a:'qwen/qwen3.8-27b'):
   value,receipt=authoring_model.generate(store,prompt,context,schema)
  raw(out/'canonical'/f'{n:03d}-output.json.gz',value);row['status']='RECEIVED'
  return value,{**receipt,'physical_calls':len(calls)-row.get('before',len(calls)-1)}
 except Exception as exc:row.update(status='FAILED',error_type=type(exc).__name__,error=str(exc));raise
 finally:put(out/'generations.json',logical)
result={'status':'STARTED','knowledge_approved':False,'published':False}
try:
 if not preflight:
  for n,h in read(DES/'freeze.json')['files'].items():assert sha(ROOT/n)==h,n
  assert read(ART/'build-ready/result.json')['ready']
  client=ExperimentClient(ROOT,out/'experiment-client',max_calls=9,max_repairs=0,schema_in_prompt=False,provider_policy=DES/'provider-policy.json')
  from observer import install as install_observer
  install_observer(client)
 w.generate=generate;domain.generate=generate
 with patch.object(dt,'post_json',observed_post):
  proposal=w.propose(change_id='actual-charter-judgment',raw_ids=[r['bundle_id']],originals=sources,query='정관 변경')
  raw(out/'proposal.json.gz',proposal);change=w.apply(**proposal);put(out/'change.json',change)
  items=w.list_items(kind='STATEMENT',limit=128)['items'];ids=[x['bundle_id'] for x in items];assert ids
  put(out/'statements.json',[w.item(i) for i in ids])
  phase='COMPILE_SELECTION'
  put(out/'compile-selection.json',{'statement_count':len(ids),'existing_limit':32,'all_preserved':True,'manual_selection_or_content_correction':False})
  compiled=compile_selection(domain,w,statement_ids=ids,purpose='정관 변경의 주주총회 결의요건과 각 비율의 기준 재사용',profile_id=p['bundle_id'],profile_work_hash=p['work_hash'])
  package=domain.preview(compiled['bundle_id']);raw(out/'compiled.json.gz',{'row':compiled,'package':package,'document':domain.load(compiled['bundle_id'])})
  result.update(status='COMPILED_AWAITING_EXPERIMENTAL_REVIEW',compiled=compiled,statements=ids,profile=p,scope=w.scope())
except Exception as exc:
 result.update(status='ADMISSION_COMPLETE' if preflight and isinstance(exc,authoring_model.AuthoringFailure) and exc.status=='HTTP_REJECTED' else 'FAILED',stage=phase,error_type=type(exc).__name__,error=str(exc))
 result['ready']=result['status']=='ADMISSION_COMPLETE';(out/'error.txt').write_text(traceback.format_exc())
finally:
 result.update(physical_calls=len(calls),unknown=sum(x['status']=='unknown' for x in calls),seconds=time.monotonic()-started,reported_cost_usd=sum((x.get('usage') or {}).get('cost',0) for x in calls),reported_tokens=sum((x.get('usage') or {}).get('total_tokens',0) for x in calls),peak_rss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
 put(out/'result.json',result);guard.done.set();guard.thread.join(timeout=2);reader.close();print(json.dumps(result,ensure_ascii=False),flush=True)
