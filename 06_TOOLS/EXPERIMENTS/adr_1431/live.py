"""One CM question through the app on the local Oracle Gold store with BGE-M3 vector initial search.

Gold connector and selected pointer are frozen copies (ART/gold-connector) so another session
changing the live pointer cannot change this cell. Observational hooks only; no product edits.
"""
from common import *
import os,time,importlib,importlib.util,traceback,resource,base64
from copy import deepcopy
from contextlib import contextmanager
os.environ.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1',AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',
                  GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),GENOS_RAG_INITIAL_SEARCH='vector')
for n in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_RAG_IMPLEMENTATION','GENOS_EMBED_URL','GENOS_EMBED_KEY'):os.environ.pop(n,None)
case_id=sys.argv[1];preflight='--preflight' in sys.argv
case=next(c for c in read(DES/'live-cases.json') if c['id']==case_id)
base=ART/('public-ready' if preflight else 'public-live')/(case_id+'-selected');base.mkdir(parents=True,exist_ok=False)
assert not (base/'STOP_EXTERNAL.json').exists()
runtime=base/'runtime';os.environ['GENOS_RUNTIME_DIR']=str(runtime)
cand=read(DES/'candidate-selected.json');C=ROOT/cand['code_root'];rel=read(DES/'baseline.json')['release']
assert all(sha(C/n)==h for n,h in cand['selected_files'].items())
freeze=read(DES/'freeze-live.json')
for p,h in freeze['files'].items():assert sha(ROOT/p)==h,p
for p,h in freeze['connector_files'].items():assert sha(ROOT/p)==h,p
from resource_guard import Guard
guard=Guard(base);guard.start()
from pinned_imports import install,verify_loaded
install(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for pkg,p in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:pkg.__path__.extend([str(C/p),str(ROOT/p)])
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
def gz(p,v):
 ref=write_raw_json(p,v);put(Path(str(p)+'.ref.json'),{'raw_json':ref})
gold_context=None;sql_request=None;sql_transport=None;store=None;client=None;calls=[];generations=[];stages=[]
try:
 gp=ART/'gold-connector';spec=importlib.util.spec_from_file_location('frozen_gold_port',gp/'connect.py');gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold)
 gold.ROOT=ROOT;gold.ACTIVE_POINTER=gp/'active-pointer.json'
 original_binding=gold.engine_binding
 def experiment_binding():
  value=original_binding()
  assert value['engine_root']==rel['code_root'] and value['engine_files']==rel['files']  # connector verified against MAIN167; candidate adds only the fix
  return {**value,'engine_root':str(C.relative_to(ROOT))}
 gold.engine_binding=experiment_binding
 allowed=set(case['document_ids'])
 gold_context=gold.open_store(documents=sorted(allowed),ontology_settings=DES/'ontology-off.json',seconds=1800,max_calls=10000)
 store,sql_request,sql_transport=gold_context.__enter__()
 profile=deepcopy(store.gold_profile);source_manifest=store.manifest
 assert profile['candidate_navigation']['ontology_enabled'] is False
 # Transport modules import semantic_runtime; the connector needs a fresh process, so load them after it.
 from lawrag.research.experiment_client import ExperimentClient
 from lawrag.research.openrouter_legal_adapter import send_reserved
 from lawrag.core import request_deadline
 verify_loaded(ART/'transport')
 # Observational: record every whole-collection read on the Oracle data objects with its caller.
 import traceback as _tb, collections as _co
 from semantic_runtime import oracle_query_matcher as _oqm, oracle_query_index as _oqi
 scans=_co.Counter()
 def _record(label):
  frames=[f for f in _tb.extract_stack(limit=14)[:-2] if 'semantic_runtime' in f.filename]
  site=' <- '.join(f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in frames[-4:])
  scans[(label,site)]+=1
 def _wrap(cls,name,label):
  orig=getattr(cls,name)
  def wrapped(self,*a,**k):
   _record(label);return orig(self,*a,**k)
  setattr(cls,name,wrapped)
 for cls,names in ((_oqm.Units,('items','__iter__')),(_oqm.SourceMetadata,('items','__iter__')),(_oqi.Sources,('__iter__',)),(_oqi.SQLMap,('items','values','__iter__'))):
  for name in names:_wrap(cls,name,cls.__name__+'.'+name)
 from semantic_runtime.app import create_app
 from semantic_runtime.provider import Haiku
 from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport,provider_request
 from semantic_runtime.legal_agent import gateway,errors
 from fastapi.testclient import TestClient
 auth_hash=sha(DES/'authorization.json');question=case['steps'][0]['question'];asked='외규: '+question;derived=set()
 class Authorized(LocalQwen38Transport):
  @property
  def public_scope(self):return tuple(sorted(allowed))
  def authorize(self,query,request,manifest,*,public_question):
   assert sha(DES/'authorization.json')==auth_hash and sha(self.policy_path)==self.policy_hash
   scope=set(query['scope']['document_version_ids'])
   assert scope and scope<=allowed and manifest['generation_id']==source_manifest['generation_id'] and manifest['store_sha256']==source_manifest['store_sha256']
   if not public_question or request.get('question',query['question']) not in {asked,question}|derived:raise errors.ContractError('Exact public question grant mismatch')
   return {'kind':'USER_AUTHORIZED_PUBLIC_CM_GOLD_VECTOR_FIX','authorization_sha256':auth_hash,'policy_sha256':self.policy_hash,'public_question_asserted':True,'scope_document_ids':sorted(scope)}
 t=Authorized(C,ROOT);profile.update(model_binding=t.binding,max_output_tokens=None)
 assert t.provider_policy==read(DES/'provider-policy.json')
 import semantic_runtime.legal_agent.unified_rag as ur_mod
 UnifiedRag=ur_mod.UnifiedRag;original_open=UnifiedRag.open
 @contextmanager
 def bound_open(host,state,principal,request):
  derived.add(host.retrieval_question(state))
  with original_open(host,state,principal,request) as execution:yield execution
 UnifiedRag.open=bound_open
 audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=40,max_repairs=0,provider_policy=DES/'provider-policy.json')
 def send(*,body,ticket):
  assert not preflight,'preflight never sends'
  if (base/'STOP_EXTERNAL.json').exists():raise errors.ContractError('Previous unknown: external sending stopped')
  allcalls=[c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]
  if len(allcalls)>=2040 or sum((c.get('usage') or {}).get('cost',0) for c in allcalls)>=10:raise errors.BudgetExhausted('Frozen experiment total budget')
  verify_loaded(ART/'transport')
  return send_reserved(audited,body=body,ticket=ticket,phase=stages[-1] if stages else 'request',error_module=errors,request_encoder=provider_request)
 t.send_once=send
 original_post=request_deadline.post_json
 def post(url,**kw):
  guard.check();payload=kw['json_body'];assert payload['model']=='qwen/qwen3.8-27b' and payload['reasoning']=={'effort':'none'}
  assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
  n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
  row={'number':n,'case_id':case_id,'stage':stages[-1] if stages else None,'canonical_number':len(generations),'status':'started','provider':payload['provider']};calls.append(row);put(base/'calls.json',calls);gz(out/'request.json.gz',payload);begin=time.monotonic()
  print('MODEL',case_id,n,row['stage'],flush=True)
  try:
   response=original_post(url,**kw)
   try:value=response.json()
   except ValueError:value={'non_json':response.text}
   gz(out/'response.json.gz',value)
   row.update(status='unknown' if response.status_code>=500 else 'responded',http_status=response.status_code,usage=value.get('usage'),actual_provider=value.get('provider'),actual_model=value.get('model'),transport_diagnostics=response.extensions.get('absolute_deadline',{}))
   if row['status']=='unknown':put(base/'STOP_EXTERNAL.json',{'cell':base.name,'call':n,'reason':'remote5xx'})
   return response
  except Exception as exc:
   row.update(status='unknown',error_type=type(exc).__name__,transport_diagnostics=getattr(exc,'diagnostics',{}))
   if hasattr(exc,'partial_body'):gz(out/'partial.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode(),'diagnostics':getattr(exc,'diagnostics',{})})
   put(base/'STOP_EXTERNAL.json',{'cell':base.name,'call':n,'reason':'Unknown physical outcome','no_automatic_retry':True});raise
  finally:row['seconds']=time.monotonic()-begin;put(out/'finished.json',row);put(base/'calls.json',calls)
 request_deadline.post_json=post
 original_generate=gateway.ModelGateway.generate
 def generate(self,phase,view,schema_name,**kwargs):
  n=len(generations)+1;stage=view.get('source_stage',phase);row={'number':n,'stage':stage};generations.append(row);stages.append(stage)
  gz(base/'canonical'/f'{n:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
  try:
   v=original_generate(self,phase,view,schema_name,**kwargs);gz(base/'canonical'/f'{n:03d}-output.json.gz',v);row['status']='accepted';return v
  except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc));raise
  finally:stages.pop();put(base/'generations.json',generations)
 gateway.ModelGateway.generate=generate
 binding={'mode':'ADR1431-gold-vector-main167-fix','case_id':case_id,'quality_certified':False}
 app=create_app(runtime,None,contracts_root=C,release=binding,provider=Haiku(C,runtime/'provider',False,backend='source-only',trust_zone='internal'),implementation='legal-agent-unified-v6',
   legal_agent_profile=profile,legal_agent_transport=t,workspace_root=ROOT,runtime_root=runtime,data_store=store,
   memory_identity=lambda request:{'user_id':'adr1431','team_id':'financial_team','document_ids':sorted(allowed)})
 client=TestClient(app,raise_server_exceptions=False);client.__enter__();assert client.get('/health').status_code==200
 loaded={n:Path(m.__file__).resolve() for n,m in list(sys.modules.items()) if n.split('.')[0]=='semantic_runtime' and getattr(m,'__file__',None)}
 def same_bytes(path):
  for root in (C,ROOT):
   if path.is_relative_to(root):
    r=str(path.relative_to(root));return r in cand['selected_files'] and sha(path)==cand['selected_files'][r]
  return False
 offenders=sorted(str(v) for v in loaded.values() if not same_bytes(v))
 assert loaded and not offenders,('every loaded semantic_runtime module must equal candidate bytes',offenders[:8])
 put(base/'binding.json',{'loaded_semantic_modules':len(loaded),'code_root':str(C),'scope':sorted(allowed),'profile':profile,'source':{k:source_manifest.get(k) for k in ('generation_id','store_sha256','export_allowed')},
   'query_release_id':getattr(sql_request,'release_id',None),'selected_pointer':read(ART/'gold-connector/active-pointer.json'),'initial_search':os.environ['GENOS_RAG_INITIAL_SEARCH'],'source_storage':'local Oracle Gold (A8_GR12_CM1208) via frozen connector','state_storage':'isolated local SQLite','oracle_writes':0})
 guard.rebase()
 body={'question':asked,'document_ids':sorted(allowed),'session_id':'adr1431-'+case_id,'request_id':'adr1431-'+case_id+'-1','use_llm':True,'team_id':'financial_team','public_question':True}
 if preflight:
  from semantic_runtime.initial_vector import Retriever
  vector=Retriever(sql_request).search(question,documents=tuple(sorted(allowed)))
  rows=vector.get('rows',[]) if isinstance(vector,dict) else []
  put(base/'vector-preflight.json',{'type':type(vector).__name__,'rows':len(rows),'embedding_calls':vector.get('embedding_calls') if isinstance(vector,dict) else None,'publication_id':vector.get('publication_id') if isinstance(vector,dict) else None,'top':[{k:r.get(k) for k in ('SOURCE_ID','DOC_ID','DISTANCE')} for r in rows[:10]]})
  put(base/'result.json',{'ready':True,'model_calls':0,'http_health':200,'vector_rows':len(rows),'sql_calls':getattr(getattr(sql_request,'sql',None),'calls',0)});print('PREFLIGHT_READY',case_id,'vector_rows',len(rows),flush=True)
 else:
  turn=base/'turn-1';turn.mkdir();put(turn/'request.json',body);begin=time.monotonic()
  r=client.post('/v1/rag/ask',json=deepcopy(body));elapsed=time.monotonic()-begin;value=r.json()
  gz(turn/'response.json.gz',{'http_status':r.status_code,'body':value})
  answer=value.get('answer') or {};text=answer.get('text','') if isinstance(answer,dict) else str(answer);(turn/'answer.txt').write_text(text)
  term=((value.get('assembly') or {}).get('term_agent') or {});reply=term.get('guided_reply') or {}
  result={'case_id':case_id,'step':case['steps'][0],'http_status':r.status_code,'request_seconds':elapsed,'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),
          'status':value.get('status'),'method':value.get('method_id'),'claims':len(answer.get('claims',[])) if isinstance(answer,dict) else 0,'needs_guidance':reply.get('needs_guidance'),'accepted_outcome':term.get('accepted_outcome')}
  if r.status_code==200:
   from semantic_runtime import chat_adapter
   try:(turn/'public-answer.txt').write_text(chat_adapter.views()._public_answer_text(value))
   except Exception as exc:put(turn/'public-answer-error.json',{'error':str(exc)})
   n=len(calls);again=client.post('/v1/rag/ask',json=deepcopy(body));dupe={'http_status':again.status_code,'same_answer':again.json().get('answer')==value.get('answer'),'extra_model_calls':len(calls)-n};put(turn/'duplicate.json',dupe);result['duplicate']=dupe
   assert dupe['same_answer'] and dupe['extra_model_calls']==0
  put(turn/'result.json',result);put(base/'result.json',{'case_id':case_id,'turns':[result],'physical_calls':len(calls),'unknown':result['unknown']});print('LIVE_RESULT',json.dumps(result,ensure_ascii=False),flush=True)
except Exception as exc:
 put(base/'runner-failure.json',{'error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'model_calls':len(calls)});raise
finally:
 if sql_transport is not None:
  try:gz(base/'sql-statements.json.gz',getattr(sql_transport,'statements',[]));gz(base/'sql-errors.json.gz',getattr(sql_transport,'errors',[]))
  except Exception as exc:put(base/'sql-log-error.json',{'error':str(exc)})
 if client is not None:client.__exit__(None,None,None)
 if gold_context is not None:gold_context.__exit__(None,None,None)
 try:put(base/'whole-scans.json',[{'call':k[0],'site':k[1],'count':v} for k,v in sorted(scans.items(),key=lambda kv:-kv[1])])
 except NameError:pass
 guard.done.set();guard.thread.join(2)
 put(base/'resource-final.json',{'sample':guard.check(),'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'candidate_unchanged':all(sha(C/n)==h for n,h in cand['selected_files'].items())})
