"""One financial CM question through the staged candidate's actual service entry on local Oracle Gold
with vector initial search; fresh Qwen3.8 through the frozen experiment transport; observational hooks only."""
from common import *
import asyncio,importlib,importlib.util,time,traceback,base64,resource,threading
from copy import deepcopy
from contextlib import contextmanager
sys.path.insert(0,str(Path(__file__).parent));import oracle_local as ol
case_id=sys.argv[1];preflight='--preflight' in sys.argv
case=next(c for c in read(DES/'live-cases.json') if c['id']==case_id)
base=ART/('public-ready' if preflight else 'public-live')/(case_id+'-candidate');base.mkdir(parents=True,exist_ok=False)
assert not (ART/'STOP_EXTERNAL.json').exists() and not (base/'STOP_EXTERNAL.json').exists()
active_pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active_pointer['generation']==178 and active_pointer['release_id']=='unread-labels-20261108-r1'
candidate=read(DES/'candidate-selected.json');C=ROOT/candidate['code_root'];gold=read(DES/'oracle-gold.json')
assert all(sha(C/n)==h for n,h in candidate['candidate_files'].items()),'candidate snapshot changed'
for p,h in read(DES/'freeze-live.json')['files'].items():assert sha(ROOT/p)==h,p
EMBED_PORT=int(os.environ.get('ADR1459_EMBED_PORT','8765'))
os.environ.update(DP='oracle',GENOS_ORACLE_TABLE_MAPPING='gold',GENOS_ORACLE_GOLD_OWNER=gold['owner'],DP_QUERY_CHANNEL=gold['channel'],
 GENOS_RAG_INITIAL_SEARCH='vector',GENOS_EMBED_URL='http://127.0.0.1:'+str(EMBED_PORT),GENOS_EMBED_MODEL='BAAI/bge-m3',GENOS_EMBED_TOKEN='local-bge-m3-experiment',
 GENOS_ORACLE_AGENT_NAMESPACE='adr1459-'+case_id+('-pre' if preflight else ''),GENOS_RUNTIME_DIR='/__oracle_agent__/runtime/adr1459',
 AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1')
for k in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_SYSTEM_LOG_DIR','GENOS_RAG_IMPLEMENTATION','DP_QUERY_RELEASE_ID','GENOS_EMBED_PROFILE_SHA256','LAWRAG_WORKSPACE_ROOT'):os.environ.pop(k,None)
from resource_guard import Guard
guard=Guard(base);guard.start()
from pinned_imports import install,verify_loaded
install(ART/'transport')
assert not any(k=='semantic_runtime' or k.startswith('semantic_runtime.') for k in sys.modules)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT)]
import lawrag,lawrag.core,lawrag.research
for pkg,p in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:pkg.__path__.extend([str(C/p),str(ROOT/p)])
from lawrag.research.experiment_client import ExperimentClient
from lawrag.research.openrouter_legal_adapter import send_reserved
from lawrag.core import request_deadline
verify_loaded(ART/'transport')
def gz(p,v):
 ref=write_raw_json(p,v);put(Path(str(p)+'.ref.json'),{'raw_json':ref})
calls=[];generations=[];stages=[];embeds=[];bridge=None;entry=None
try:
 import requests
 original_session_post=requests.Session.post
 def session_post(self,url,**kw):
  begin=time.monotonic();response=original_session_post(self,url,**kw)
  if '/embeddings' in url:
   embeds.append({'url':url,'status':response.status_code,'seconds':round(time.monotonic()-begin,3),'inputs':len((kw.get('json') or {}).get('input') or []),'stage':stages[-1] if stages else 'request'})
   put(base/'embedding-calls.json',embeds)
  return response
 requests.Session.post=session_post
 health=requests.get('http://127.0.0.1:%d/health'%EMBED_PORT,timeout=5);assert health.status_code==200,'embedding endpoint not ready'
 spec=importlib.util.spec_from_file_location('candidate_service',C/'service.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
 from semantic_runtime import oracle_query_service as serving,oracle_dp
 from semantic_runtime.oracle_gold_mapping import GoldMapping
 # Local Gold keeps the pre-registration physical names/widths (IDD_B03_*, SRCH_ROW RFRN_DATA_*, wider IDs);
 # the registered R5 mapping is rebound to them from Oracle metadata. Logical columns, keys and readers are unchanged.
 registered=GoldMapping.load(owner=gold['owner'])
 mapping,mapping_changes=ol.local_gold_mapping(registered,ol.connect(),owner=gold['owner'])
 bridge=ol.Bridge(mapping,log_path=base/'sql-calls.jsonl')
 serving.client_from_environment=lambda:bridge
 serving.Factory.start_recovery=lambda self:None
 oracle_dp.prepare=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('source corpus download attempted'))
 entry._local_release=lambda:(_ for _ in ()).throw(RuntimeError('local source release fallback attempted'))
 factory=entry._oracle_factory()
 assert factory.channel==gold['channel'] and factory.transport is None,'GENOS LLM env unexpectedly configured'
 package='semantic_runtime'
 mod=lambda name:importlib.import_module(package+'.legal_agent.'+name)
 gateway=mod('gateway');errors=mod('errors');local=mod('local_gemma');policy=mod('workflow_tiers_policy')
 # The Oracle factory binds a model only from GENOS_LLM_*; this experiment binds the same local
 # external transport the local release uses (service.py local-release path), unchanged product code.
 t=local.LocalQwen38Transport(C,ROOT);pinned=entry._json(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
 factory.profile=policy.profile(entry._investigation_profile(entry._genos_v5_wait_profile(entry._genos_v5_admission_profile({**pinned,'model_binding':t.binding,'max_output_tokens':t.policy['max_output_tokens'],
  'max_transport_retries':(pinned.get('max_transport_retries',0) if pinned.get('candidate_navigation',{}).get('completion_contract') else 0)}))),require_model=True)
 factory.transport=serving.ValidatedTransport(t)
 assert mod('reason_decision_review').enabled(factory.profile) and factory.profile['max_model_attempts']==40 and factory.profile['max_output_tokens'] is None
 assert t.provider_policy==read(DES/'provider-policy.json')
 granted=set(case['document_ids']);assert granted<=set(t.grant['public_document_ids'])
 team_scope=importlib.import_module(package+'.team_scope')
 with serving.request_context():
  app0=factory.application();allowed=granted&set(team_scope.select_documents(app0.state.pipeline.store,'financial_team'))
  binding0=dict(app0.state.oracle_binding)
 assert allowed and binding0['query_channel']==gold['channel'] and binding0['data_provider']=='oracle'
 put(base/'scope-selection.json',{'requested_public_grant':sorted(granted),'actual_financial_team_intersection':sorted(allowed),'excluded_outside_current_team':sorted(granted-allowed),'oracle_binding':binding0,'reference_answers_used':False})
 views=importlib.import_module(package+'.chat_adapter').views()
 question=case['steps'][0]['question'];body=views._request_body(question,{'applied_fields':{'mode':'외규'},'team_id':'financial_team','session_id':'adr1459-'+case_id,'request_id':'adr1459-'+case_id+'-1','document_ids':sorted(allowed),'memory':True,'public_question':True,'use_llm':True});body['public_question']=True
 assert body['question']=='외규: '+question
 derived=set();derivations=[];authhash=sha(DES/'authorization.json')
 original_authorize=t.authorize
 def authorize(query,request,manifest,*,public_question):
  assert sha(DES/'authorization.json')==authhash
  scope=set(query['scope']['document_version_ids']);assert scope and scope<=allowed
  assert manifest['generation_id']==binding0['generation_id'] and manifest.get('dataset_version',gold['dataset_version'])==gold['dataset_version']
  assert request.get('question',query['question']) in {body['question'],question}|derived
  receipt=original_authorize(query,request,manifest,public_question=public_question)
  return {**receipt,'experiment_authorization':authhash,'source':'local-oracle-gold'}
 t.authorize=authorize
 UnifiedRag=mod('unified_rag').UnifiedRag;original_open=UnifiedRag.open
 @contextmanager
 def bound_open(host,state,principal,request):
  assert request['request_id']==body['request_id'] and request['question']==body['question']
  assert state['document_ids'] and set(state['document_ids'])<=allowed
  effective=host.retrieval_question(state);derived.add(effective)
  derivations.append({'original_question':body['question'],'effective_question':effective,'task':state['task'],'facts':deepcopy(state['facts']),'document_ids':state['document_ids'],'product_state_rewritten':False});put(base/'authorized-derivations.json',derivations)
  with original_open(host,state,principal,request) as execution:yield execution
 UnifiedRag.open=bound_open
 audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=40,max_repairs=0,provider_policy=DES/'provider-policy.json')
 def send(*,body,ticket):
  assert not preflight,'preflight never sends'
  if (ART/'STOP_EXTERNAL.json').exists() or (base/'STOP_EXTERNAL.json').exists():raise errors.ContractError('Previous unknown: external sending stopped')
  allcalls=[c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]
  if len(allcalls)>=360 or sum((c.get('usage') or {}).get('cost',0) for c in allcalls)>=3:raise errors.BudgetExhausted('Frozen experiment total budget')
  verify_loaded(ART/'transport')
  return send_reserved(audited,body=body,ticket=ticket,phase=stages[-1] if stages else 'request',error_module=errors,request_encoder=local.provider_request)
 t.send_once=send
 original_post=request_deadline.post_json
 def post(url,**kw):
  guard.check();payload=kw['json_body'];assert payload['model']=='qwen/qwen3.8-27b' and payload['reasoning']=={'effort':'none'}
  assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
  n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
  row={'number':n,'case_id':case_id,'stage':stages[-1] if stages else None,'canonical_number':len(generations),'status':'started','provider':payload['provider'],'sql_calls_so_far':bridge.count};calls.append(row);put(base/'calls.json',calls);gz(out/'request.json.gz',payload);begin=time.monotonic()
  print('MODEL',case_id,n,row['stage'],'sql',bridge.count,flush=True)
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
 loaded={n:Path(m.__file__).resolve() for n,m in list(sys.modules.items()) if n.split('.')[0]=='semantic_runtime' and getattr(m,'__file__',None)}
 offenders=sorted(str(v) for v in loaded.values() if not v.is_relative_to(C))
 assert loaded and not offenders,('every loaded semantic_runtime module must come from the candidate tree',offenders[:8])
 put(base/'binding.json',{'arm':'candidate','loaded_semantic_modules':len(loaded),'code_root':str(C),'scope':sorted(allowed),'profile':factory.profile,'oracle':gold,'oracle_binding':binding0,'physical_mapping':{'registered_sha256':registered.target_sha256,'local_variant_sha256':mapping.target_sha256,'changes':mapping_changes},'service_entry':str(C/'service.py'),'selected_pointer':active_pointer,'source_storage':'local Oracle Gold via direct SQL bridge (ORDS envelope replaced)','state_storage':'Oracle agent records (SIDDA), namespace '+os.environ['GENOS_ORACLE_AGENT_NAMESPACE'],'embedding':'local BAAI/bge-m3 HTTP endpoint on 127.0.0.1:'+str(EMBED_PORT),'initial_search':'vector','actual_default_profile':True,'oracledb_loaded':'oracledb' in sys.modules})
 health=asyncio.run(entry.service({},{'API_TYPE':'HEALTH'}));assert health['status']==200,health
 guard.rebase()
 if preflight:
  # No model: vector retrieval through the same service reader, plus the named-article resolver on the Oracle matcher.
  from semantic_runtime.document_agent import ServingDocumentAgent
  from semantic_runtime.oracle_query_vector import Retriever
  with serving.request_context():
   app=factory.application();agent=ServingDocumentAgent(app.state.pipeline,app.state.pipeline.term_agent.config)
   with agent.resources(sorted(allowed)) as (_,tools,glossary,matcher):
    assert isinstance(matcher.initial_vector,Retriever)
    result=matcher.initial_vector.search(question,set(allowed))
    rows=[{'document':str(matcher.documents.get(r['DOC_ID'],'')).rsplit(' > ',1)[-1],'source_id':r['SOURCE_ID'],'distance':float(r['DISTANCE']),'heading':(tools.sources.get(r['SOURCE_ID']) or {}).get('heading')} for r in result['rows'][:10]]
    from types import SimpleNamespace as NS
    ga=mod('guided_answer');sess=NS(matcher=matcher,scope=set(allowed),tools=tools)
    resolved={frag:ga.resolve_named_article(sess,frag)[0] or ga.resolve_named_article(sess,frag)[1] for frag in ['상법 제341조의4','상속세 및 증여세법 제41조의3','자본시장과 금융투자업에 관한 법률 시행령 제125조','상속세 및 증여세법 제45조의6']}
  put(base/'result.json',{'ready':True,'model_calls':0,'http_health':200,'vector_rows':len(result['rows']),'embedding_calls':result['embedding_calls'],'top':rows,'named_article_resolution':resolved,'sql':bridge.summary(),'embedding_http_calls':embeds});print('PREFLIGHT_READY',case_id,json.dumps(rows[:5],ensure_ascii=False),flush=True)
 else:
  turn=base/'turn-1';turn.mkdir();put(turn/'request.json',body);begin=time.monotonic();sql_before=bridge.count;response=asyncio.run(entry.service({},deepcopy(body)));elapsed=time.monotonic()-begin
  value=response.get('body') or {};gz(turn/'response.json.gz',{'http_status':response['status'],'body':value})
  answer=value.get('answer') or {};text=answer.get('text','') if isinstance(answer,dict) else str(answer);(turn/'answer.txt').write_text(text)
  term=((value.get('assembly') or {}).get('term_agent') or {});reply=term.get('guided_reply') or {}
  result={'needs_guidance':reply.get('needs_guidance'),'accepted_outcome':term.get('accepted_outcome'),'case_id':case_id,'step':case['steps'][0],'http_status':response['status'],'request_seconds':elapsed,'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),'goal_id':value.get('goal_id'),'revision':value.get('revision'),'status':value.get('status'),'method':value.get('method_id'),'executed':value.get('executed'),'claims':len(answer.get('claims',[])) if isinstance(answer,dict) else 0,
   'sql_calls':bridge.count-sql_before,'sql_seconds':round(bridge.seconds,3),'embedding_calls':len(embeds),'named_article_lookup':reply.get('named_article_lookup'),'proposed_reads':[{k:r.get(k) for k in ('read_id','label','origin')} for r in reply.get('proposed_reads',[])],'reference_normalizations':reply.get('reference_normalizations')}
  if response['status']==200:
   (turn/'public-answer.txt').write_text(views._public_answer_text(value));count=len(calls);sql_mid=bridge.count;again=asyncio.run(entry.service({},deepcopy(body)));dupe={'http_status':again['status'],'same_answer':again.get('body',{}).get('answer')==value.get('answer'),'extra_model_calls':len(calls)-count,'sql_calls':bridge.count-sql_mid};put(turn/'duplicate.json',dupe);result['duplicate']=dupe
   assert dupe['same_answer'] and dupe['extra_model_calls']==0
  put(turn/'result.json',result);put(base/'result.json',{'case_id':case_id,'turns':[result],'physical_calls':len(calls),'unknown':result['unknown'],'sql':bridge.summary()});print('LIVE_RESULT',json.dumps({k:result[k] for k in ('case_id','http_status','request_seconds','physical_calls','claims','needs_guidance','sql_calls','embedding_calls','named_article_lookup','proposed_reads')},ensure_ascii=False),flush=True)
 try:entry.request_report._FINALIZER_QUEUE.join()
 except Exception:pass
except Exception as exc:
 put(base/'runner-failure.json',{'error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'model_calls':len(calls)});raise
finally:
 guard.done.set();guard.thread.join(2)
 put(base/'resource-final.json',{'sample':guard.check(),'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'candidate_unchanged':all(sha(C/n)==h for n,h in candidate['candidate_files'].items()),'oracle_driver_loaded':'oracledb' in sys.modules,'sql':bridge.summary() if bridge else None,'embedding_http_calls':len(embeds)})
