"""One financial CM question through the candidate's actual service entry (explicit generation mode,
same dataset as local Oracle Gold) with vector initial search whose candidates come from the Oracle
Gold bge-m3 items (A8_GR12_CM1208) through the local bge-m3 endpoint. Fresh Qwen3.8 via the frozen
experiment transport; observational hooks only.

Why hybrid: native DP=oracle serving of this code needs a fresh query publication (33.2M rows for
the 21 documents) that Oracle Free's 12 GB database limit rejects (ORA-12954, design/deviation.json).
Originals, agent records and structure come from the selected generation (dataset d4d1d8b4…, the
same bytes the Gold DOC_* tables hold); only the initial vector candidates come from Oracle."""
from common import *
import asyncio,importlib,importlib.util,time,traceback,base64,resource,math
from copy import deepcopy
from contextlib import contextmanager
sys.path.insert(0,str(Path(__file__).parent));import oracle_local as ol
case_id=sys.argv[1];preflight='--preflight' in sys.argv
case=next(c for c in read(DES/'live-cases.json') if c['id']==case_id)
base=ART/('public-ready' if preflight else 'public-live')/(case_id+'-candidate');base.mkdir(parents=True,exist_ok=False)
assert not (ART/'STOP_EXTERNAL.json').exists()
active_pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')  # recorded only; the candidate is a frozen snapshot, not the selected MAIN
candidate=read(DES/'candidate-selected.json');C=ROOT/candidate['code_root'];gold=read(DES/'oracle-gold.json');deviation=read(DES/'deviation.json')
assert all(sha(C/n)==h for n,h in candidate['candidate_files'].items()),'candidate snapshot changed'
for p,h in read(DES/'freeze-live.json')['files'].items():assert sha(ROOT/p)==h,p
GENERATION=(ROOT/read(DES/'baseline.json')['release']['data_path']).resolve();assert GENERATION.is_dir()
EMBED_PORT=int(os.environ.get('ADR1468_EMBED_PORT','8765'))
os.environ.update(GENOS_GENERATION=str(GENERATION),GENOS_RAG_INITIAL_SEARCH='hybrid',GENOS_RUNTIME_DIR=str(base/'runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1')
for k in ('DP','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR','GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_RAG_IMPLEMENTATION','GENOS_LLM_URL','GENOS_LLM_KEY','GENOS_LLM_SERVING_ID','GENOS_LLM_MODEL','GENOS_EMBED_URL','GENOS_EMBED_MODEL','GENOS_EMBED_TOKEN'):os.environ.pop(k,None)
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
calls=[];generations=[];stages=[];embeds=[];vector_sql=[];entry=None;app=None
try:
 import requests
 health=requests.get('http://127.0.0.1:%d/health'%EMBED_PORT,timeout=5);assert health.status_code==200,'embedding endpoint not ready'
 spec=importlib.util.spec_from_file_location('candidate_service',C/'service.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
 package='semantic_runtime';mod=lambda name:importlib.import_module(package+'.legal_agent.'+name)
 gateway=mod('gateway');errors=mod('errors');local=mod('local_gemma');policy=mod('workflow_tiers_policy')
 # Explicit-generation mode binds a model only from GENOS_LLM_*; bind the same local external
 # transport the local release uses (service.py local-release path), product code unchanged.
 t=local.LocalQwen38Transport(C,ROOT);pinned=entry._json(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
 configured=policy.profile({**pinned,'model_binding':t.binding,'max_output_tokens':t.policy['max_output_tokens'],
  'max_transport_retries':(pinned.get('max_transport_retries',0) if pinned.get('candidate_navigation',{}).get('completion_contract') else 0)},require_model=True)
 entry._genos_v5_environment_binding=lambda request_profile=None:(configured,t)
 # Vector initial search: candidates from the Oracle Gold bge-m3 items; unit -> source through the session matcher.
 nm=importlib.import_module(package+'.navigation_match');iv=importlib.import_module(package+'.initial_vector')
 oracle=ol.connect();GOLD_DOCS=set(gold['documents']);VID=gold['vector_post_id'];OWNER=gold['owner']
 class GoldVectorRetriever:
  def __init__(self,matcher):self.matcher=matcher;self.calls=0;self.cache={}
  def search(self,question,documents,source_ids=None):
   documents=set(documents)&GOLD_DOCS
   if not documents or source_ids==[]:return {'publication_id':None,'revision':None,'rows':[],'embedding_calls':0,'truncated':False}
   key=hashlib.sha256(json.dumps([question,sorted(documents),source_ids],ensure_ascii=False).encode()).hexdigest()
   if key in self.cache:return self.cache[key]
   begin=time.monotonic();r=requests.post('http://127.0.0.1:%d/v1/embeddings'%EMBED_PORT,json={'model':'BAAI/bge-m3','input':[question]},timeout=30);r.raise_for_status()
   vector=iv.normalize(r.json()['data'][0]['embedding'],1024);self.calls+=1
   embeds.append({'stage':stages[-1] if stages else 'request','seconds':round(time.monotonic()-begin,3),'chars':len(question)});put(base/'embedding-calls.json',embeds)
   cur=oracle.cursor();begin=time.monotonic()
   cur.execute(f"SELECT RGLT_DOC_ID,BODY_UNIT_ID,MIN(VECTOR_DISTANCE(EMBD_VCTR,TO_VECTOR(:v),COSINE)) AS D FROM {OWNER}.IDD_B03_LGL_VCTR_ITEM WHERE VCTR_POST_ID=:p AND RGLT_DOC_ID IN (SELECT j.did FROM JSON_TABLE(:docs,'$[*]' COLUMNS(did VARCHAR2(1000) PATH '$')) j) GROUP BY RGLT_DOC_ID,BODY_UNIT_ID ORDER BY D,RGLT_DOC_ID,BODY_UNIT_ID FETCH FIRST 150 ROWS ONLY",
    {'v':json.dumps(vector),'p':VID,'docs':json.dumps(sorted(documents))})
   hits=cur.fetchall();vector_sql.append({'seconds':round(time.monotonic()-begin,3),'hits':len(hits)});cur.close()
   rows=[];seen=set()
   for did,uid,dist in hits:
    try:sids=[s for s in (self.matcher._unit_sources(did,str(uid)) or []) if self.matcher.sources[s]['document_id']==did]
    except Exception:sids=[]
    for sid in sids[:1]:
     if sid in seen or (source_ids is not None and sid not in source_ids):continue
     seen.add(sid);rows.append({'DOC_ID':did,'SOURCE_ID':sid,'DISTANCE':float(dist)})
    if len(rows)>=100:break
   result={'publication_id':VID,'revision':int(gold.get('vector_revision') or 3),'rows':rows,'embedding_calls':self.calls,'truncated':len(rows)>=100}
   self.cache[key]=result;return result
 def _initial_vector(self):
  if '_adr1459_vector' not in self.__dict__:self.__dict__['_adr1459_vector']=GoldVectorRetriever(self)
  return self.__dict__['_adr1459_vector']
 nm.ReverseMatcher.initial_vector=property(_initial_vector)
 app=entry.application();assert Path(app.state.pipeline.contracts.root)==C,app.state.pipeline.contracts.root
 assert entry._BINDING['mode']=='genos-generation' and entry._BINDING['generation_id']==read(GENERATION/'manifest.json')['generation_id']
 agent=app.state.pipeline.term_agent;assert agent.transport is t and agent.profile['max_model_attempts']==40 and agent.profile['max_output_tokens'] is None
 assert mod('reason_decision_review').enabled(agent.profile) and t.provider_policy==read(DES/'provider-policy.json')
 # Request scope as in ADR-1458/1424: the public grant intersected with the current financial team.
 # The Gold vector items cover the 21 Gold documents inside that scope (vector_documents); keyword search covers the rest.
 granted=set(t.grant['public_document_ids']);assert GOLD_DOCS<=granted and set(case['document_ids'])==GOLD_DOCS
 team_scope=importlib.import_module(package+'.team_scope')
 allowed=granted&set(team_scope.select_documents(app.state.pipeline.store,'financial_team'));assert allowed
 vector_docs=GOLD_DOCS&allowed;assert len(vector_docs)>=19,sorted(GOLD_DOCS-allowed)  # two Gold documents (중소기업 법령) are outside the financial team
 put(base/'scope-selection.json',{'requested_public_grant':sorted(granted),'actual_financial_team_intersection':sorted(allowed),'excluded_outside_current_team':sorted(granted-allowed),'vector_documents':sorted(vector_docs),'gold_documents_outside_scope':sorted(GOLD_DOCS-allowed),'vector_coverage':str(len(vector_docs))+' of '+str(len(allowed))+' scope documents','reference_answers_used':False})
 metadata=read(GENERATION/'manifest.json');assert sha(GENERATION/'manifest.json')==gold['dataset_version'],'generation differs from the Gold dataset'
 views=importlib.import_module(package+'.chat_adapter').views()
 question=case['steps'][0]['question'];body=views._request_body(question,{'applied_fields':{'mode':'외규'},'team_id':'financial_team','session_id':'adr'+TARGET+'-'+case_id,'request_id':'adr'+TARGET+'-'+case_id+'-1','document_ids':sorted(allowed),'memory':True,'public_question':True,'use_llm':True});body['public_question']=True
 assert body['question']=='외규: '+question
 derived=set();derivations=[];authhash=sha(DES/'authorization.json')
 normalized,principal=mod('memory_identity').prepare(app.state.pipeline,base/'runtime',entry._normalize(deepcopy(body))['json'],require_memory=True)
 assert set(body['document_ids'])<=set(principal['document_ids'])
 original_authorize=t.authorize
 def authorize(query,request,manifest,*,public_question):
  assert sha(DES/'authorization.json')==authhash
  scope=set(query['scope']['document_version_ids']);assert scope and scope<=allowed,('scope outside allowed',len(scope),len(allowed),sorted(scope-allowed)[:5])
  assert manifest['generation_id']==metadata['generation_id'] and manifest['store_sha256']==metadata['store_sha256']
  assert request.get('question',query['question']) in {body['question'],question}|derived
  receipt=original_authorize(query,request,manifest,public_question=public_question)
  return {**receipt,'experiment_authorization':authhash}
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
  if os.environ.get('ADR1468_DRYRUN'):raise errors.ContractError('ADR1468 dry run: no model call')
  if (ART/'STOP_EXTERNAL.json').exists() or (base/'STOP_EXTERNAL.json').exists():raise errors.ContractError('Previous unknown: external sending stopped')
  allcalls=[c for p in (ART/'public-live').glob('*/calls.json') for c in read(p)]
  if len(allcalls)>=80 or sum((c.get('usage') or {}).get('cost',0) for c in allcalls)>=1:raise errors.BudgetExhausted('Frozen experiment total budget')
  verify_loaded(ART/'transport')
  return send_reserved(audited,body=body,ticket=ticket,phase=stages[-1] if stages else 'request',error_module=errors,request_encoder=local.provider_request)
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
 loaded={n:Path(m.__file__).resolve() for n,m in list(sys.modules.items()) if n.split('.')[0]=='semantic_runtime' and getattr(m,'__file__',None)}
 offenders=sorted(str(v) for v in loaded.values() if not v.is_relative_to(C))
 assert loaded and not offenders,('every loaded semantic_runtime module must come from the candidate tree',offenders[:8])
 put(base/'binding.json',{'arm':'candidate','mode':'hybrid','loaded_semantic_modules':len(loaded),'code_root':str(C),'scope':sorted(allowed),'profile':agent.profile,'service_binding':entry._BINDING,'generation':str(GENERATION),'oracle_vectors':{'owner':OWNER,'vector_post_id':VID,'documents':len(GOLD_DOCS)},'deviation':deviation,'selected_pointer':active_pointer,'source_storage':'selected generation SQLite (same dataset as Gold DOC_*)','state_storage':'isolated local SQLite runtime','embedding':'local BAAI/bge-m3 HTTP endpoint on 127.0.0.1:'+str(EMBED_PORT),'initial_search':'vector (Oracle Gold items)','actual_default_profile':True})
 health=asyncio.run(entry.service({},{'API_TYPE':'HEALTH'}));assert health['status']==200,health
 guard.rebase()
 if preflight:
  from semantic_runtime.document_agent import ServingDocumentAgent
  agent2=ServingDocumentAgent(app.state.pipeline,app.state.pipeline.term_agent.config)
  with agent2.resources(sorted(allowed)) as (_,tools,glossary,matcher):
   result=matcher.initial_vector.search(question,set(allowed))
   rows=[{'document':str(matcher.documents.get(r['DOC_ID'],'')).rsplit(' > ',1)[-1],'source_id':r['SOURCE_ID'],'distance':round(r['DISTANCE'],4),'heading':(tools.sources.get(r['SOURCE_ID']) or {}).get('heading')} for r in result['rows'][:10]]
   from types import SimpleNamespace as NS
   ga=mod('guided_answer');sess=NS(matcher=matcher,scope=set(allowed),tools=tools)
   resolved={frag:(ga.resolve_named_article(sess,frag)[0] or ga.resolve_named_article(sess,frag)[1]) for frag in ['상법 제341조의4','상속세 및 증여세법 제41조의3','자본시장과 금융투자업에 관한 법률 시행령 제125조','상속세 및 증여세법 제45조의6']}
  put(base/'result.json',{'ready':True,'model_calls':0,'http_health':200,'vector_rows':len(result['rows']),'embedding_calls':result['embedding_calls'],'top':rows,'named_article_resolution':resolved,'vector_sql':vector_sql});print('PREFLIGHT_READY',case_id,json.dumps(rows[:5],ensure_ascii=False),flush=True)
 else:
  turn=base/'turn-1';turn.mkdir();put(turn/'request.json',body);begin=time.monotonic();response=asyncio.run(entry.service({},deepcopy(body)));elapsed=time.monotonic()-begin
  value=response.get('body') or {};gz(turn/'response.json.gz',{'http_status':response['status'],'body':value})
  answer=value.get('answer') or {};text=answer.get('text','') if isinstance(answer,dict) else str(answer);(turn/'answer.txt').write_text(text)
  term=((value.get('assembly') or {}).get('term_agent') or {});reply=term.get('guided_reply') or {}
  result={'needs_guidance':reply.get('needs_guidance'),'accepted_outcome':term.get('accepted_outcome'),'case_id':case_id,'step':case['steps'][0],'http_status':response['status'],'request_seconds':elapsed,'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),'goal_id':value.get('goal_id'),'revision':value.get('revision'),'status':value.get('status'),'method':value.get('method_id'),'executed':value.get('executed'),'claims':len(answer.get('claims',[])) if isinstance(answer,dict) else 0,
   'embedding_calls':len(embeds),'vector_sql':vector_sql,'named_article_lookup':reply.get('named_article_lookup'),'proposed_reads':[{k:r.get(k) for k in ('read_id','label','origin')} for r in reply.get('proposed_reads',[])],'reference_normalizations':reply.get('reference_normalizations')}
  if response['status']==200:
   (turn/'public-answer.txt').write_text(views._public_answer_text(value));count=len(calls);again=asyncio.run(entry.service({},deepcopy(body)));dupe={'http_status':again['status'],'same_answer':again.get('body',{}).get('answer')==value.get('answer'),'extra_model_calls':len(calls)-count};put(turn/'duplicate.json',dupe);result['duplicate']=dupe
   assert dupe['same_answer'] and dupe['extra_model_calls']==0
  put(turn/'result.json',result);put(base/'result.json',{'case_id':case_id,'turns':[result],'physical_calls':len(calls),'unknown':result['unknown']});print('LIVE_RESULT',json.dumps({k:result[k] for k in ('case_id','http_status','request_seconds','physical_calls','claims','needs_guidance','embedding_calls','named_article_lookup','proposed_reads')},ensure_ascii=False),flush=True)
 try:entry.request_report._FINALIZER_QUEUE.join()
 except Exception:pass
except Exception as exc:
 put(base/'runner-failure.json',{'error_type':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(),'model_calls':len(calls)});raise
finally:
 if app is not None:
  try:app.state.pipeline.store.close()
  except Exception:pass
 guard.done.set();guard.thread.join(2)
 put(base/'resource-final.json',{'sample':guard.check(),'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'candidate_unchanged':all(sha(C/n)==h for n,h in candidate['candidate_files'].items()),'embedding_http_calls':len(embeds),'vector_sql_calls':len(vector_sql)})
