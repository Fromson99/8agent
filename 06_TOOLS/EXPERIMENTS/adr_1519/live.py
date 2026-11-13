"""ADR-1519: one 대사 case on one arm through that arm's own service.py entry in a fresh process;
fresh Qwen3.8 through the pinned experiment transport; observational hooks only.

  live.py <case_id> <baseline|candidate> [--preflight] [--rerun]

--rerun: once more, alone, after a provider failure (unknown/blank/5xx) in the first run; both runs are kept.

The arm's code root (release folder / staged candidate) is hash-checked before and after. Local SQLite
generation, isolated runtime under live/<arm>/<case>. No local vector publication for these documents, so the
product's own fallback (body search) runs. Records per request: physical calls, unknown outcomes, model
seconds, process CPU seconds, and the comparison table (rows, sides, verdicts, failure points)."""
from common import *
import asyncio,importlib,importlib.util,time,traceback,base64,resource
from copy import deepcopy
from types import MappingProxyType
case_id=sys.argv[1];ARM=sys.argv[2];assert ARM in ('baseline','candidate');MODE='preflight' if '--preflight' in sys.argv else 'live';RERUN='--rerun' in sys.argv
for p,h in read(DES/'freeze.json')['files'].items():assert sha(ROOT/p)==h,('frozen file changed',p)
case=next(c for c in read(DES/'cases.json') if c['id']==case_id)
code=read(DES/('code-'+ARM+'.json'));C=ROOT/code['code_root'];files=code['files']
limits=read(DES/'criteria.json')['limits']
gspec=read(DES/'generations.json')[case['generation']];GEN=ROOT/gspec['path'];assert sha(GEN/'manifest.json')==gspec['manifest_sha256']
metadata=read(GEN/'manifest.json')
base=ART/('preflight' if MODE=='preflight' else 'live')/ARM/(case_id+('-rerun' if RERUN else ''));base.mkdir(parents=True,exist_ok=False)
assert not RERUN or (ART/'live'/ARM/case_id/'STOP_EXTERNAL.json').exists() or (ART/f'yield-{case_id}.json').exists(),'a rerun follows a failure of every provider or a memory yield of the same cell'
os.environ.update(GENOS_RUNTIME_DIR=str(base/'runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),
                  GENOS_RAG_INITIAL_SEARCH='hybrid',OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1')
for k in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE','GENOS_STATE_DIR',
          'GENOS_SHARED_LOG_DIR','GENOS_DETAIL_LOG_DIR','GENOS_RAG_IMPLEMENTATION','GENOS_DELEGATION_LINKS','GENOS_LLM_URL','GENOS_LLM_KEY','GENOS_EMBED_URL','LOG','GENOS_LOG','GENOS_LIVE_LOG','GENOS_COMPARE_FLOW'):
    os.environ.pop(k,None)
key_env=read(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['key_env']
if not os.environ.get(key_env):
    from dotenv import dotenv_values
    value=dotenv_values(ROOT/'.env').get(key_env);assert value,'workspace credential missing';os.environ[key_env]=value
class Idle:
    def check(self,startup=False):return None
    def rebase(self):return None
if MODE=='live':
    from resource_guard import Guard
    guard=Guard(base);guard.start()
else:guard=Idle()
from pinned_imports import install,verify_loaded
install(ART/'transport')
assert not any(k=='semantic_runtime' or k.startswith('semantic_runtime.') for k in sys.modules)
sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(ROOT)]
import lawrag,lawrag.core,lawrag.research
for pkg,p in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:pkg.__path__.extend([str(C/p),str(ROOT/p)])
from lawrag.research.experiment_client import ExperimentClient
from lawrag.research.openrouter_legal_adapter import send_reserved
from lawrag.research.provider_fallback import load_policy as load_fallback,send_with_fallback
from lawrag.core import request_deadline
verify_loaded(ART/'transport')
app=None;calls=[];generations=[];stages=[];embeds=[];vector_sql=[];cpu_marks={}
def code_unchanged():return all(sha(C/n)==h for n,h in files.items())
try:
    spec=importlib.util.spec_from_file_location('arm_service',C/'service.py');entry=importlib.util.module_from_spec(spec)
    sys.modules['arm_service']=entry;spec.loader.exec_module(entry)
    def local_release():
        return C.resolve(),GEN.resolve(),{'mode':'local-release','release_id':code['release_id'],'generation':None,'experiment':ADR.name,
            'release_manifest_sha256':code['release_manifest_sha256'],
            'code_sha256':hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'data_manifest_sha256':gspec['manifest_sha256'],
            'source_generation_id':metadata['generation_id'],'fulltext_manifest_sha256':(metadata.get('fulltext') or {}).get('manifest_sha256'),
            'process_instance_id':entry._PROCESS_INSTANCE_ID,'process_id':os.getpid()}
    entry._local_release=local_release
    app=entry.application();assert Path(app.state.pipeline.contracts.root).resolve()==C.resolve()
    package=type(app.state.pipeline).__module__.rsplit('.',1)[0]
    mod=lambda name:importlib.import_module(package+'.legal_agent.'+name)
    agent=app.state.pipeline.term_agent;t=agent.transport;gateway=mod('gateway');errors=mod('errors');local=mod('local_gemma')
    assert t.provider_policy==read(DES/'provider-policy.json')
    store=app.state.pipeline.store;allowed=set(case['document_ids'])
    # Team membership for test-generation documents that carry it only under source_metadata (as ADR-1487/1503).
    ts=importlib.import_module(package+'.team_scope');native=ts.document_teams(store)
    missing={d:frozenset({case['team']}) for d in allowed if case['team'] not in native.get(d,frozenset())}
    if missing:
        store._projected_teams=MappingProxyType(missing);ts._CACHE.clear()
    assert set(ts.select_documents(store,case['team']))>=allowed
    authhash=sha(DES/'authorization.json')
    question_ok={case['question']}
    def authorize(query,request,manifest,*,public_question):
        """Experiment grant (user 2026-11-12: every document may be sent): scope inside the case's team documents,
        the frozen generation, policy files unchanged. Child RAGs of a workflow inherit its receipt."""
        assert sha(DES/'authorization.json')==authhash and sha(t.policy_path)==t.policy_hash
        scope=set(query['scope']['document_version_ids']);assert scope and scope<=allowed,('scope outside the case',len(scope-allowed))
        assert manifest['generation_id']==metadata['generation_id'] and manifest['store_sha256']==metadata['store_sha256']
        parent=mod('workflow_execution').authorization()
        if parent is not None:
            assert parent['kind']=='USER_AUTHORIZED_WORKFLOW' and parent.get('experiment_authorization')==authhash and not scope-set(parent['scope_document_ids'])
            return {**parent,'scope_document_ids':sorted(scope)}
        return {'grant_sha256':t.grant_hash,'policy_sha256':t.policy_hash,'public_question_asserted':True,'scope_document_ids':sorted(scope),'experiment_authorization':authhash}
    def authorize_workflow(request,binding):
        assert request.get('workflow_id') and set(request['document_ids'])<=allowed and request['document_ids']
        assert binding['generation_id']==metadata['generation_id'] and binding['store_sha256']==metadata['store_sha256']
        return {'kind':'USER_AUTHORIZED_WORKFLOW','grant_sha256':t.grant_hash,'policy_sha256':t.policy_hash,'scope_document_ids':request['document_ids'],
                'generation_id':binding['generation_id'],'store_sha256':binding['store_sha256'],'principal':request['principal'],
                'public_question_asserted':False,'experiment_authorization':authhash}
    t.authorize=authorize;t.authorize_workflow=authorize_workflow
    t.grant=dict(t.grant,public_document_ids=sorted(allowed))
    assert not case['vector'],'ADR-1519 cases have no vector publication'
    if case['vector']:
        import requests
        sys.path.insert(0,str(TOOLS));import oracle_local as ol
        port=int(os.environ.get('ADR_EMBED_PORT','8765'))
        assert requests.get('http://127.0.0.1:%d/health'%port,timeout=5).status_code==200,'embedding endpoint not ready'
        gold=read(DES/'oracle-gold.json');GOLD=set(gold['documents']);VID=gold['vector_post_id'];OWNER=gold['owner']
        nm=importlib.import_module(package+'.navigation_match');iv=importlib.import_module(package+'.initial_vector')
        oracle=ol.connect()
        class GoldVectorRetriever:
            def __init__(self,matcher):self.matcher=matcher;self.calls=0;self.cache={}
            def search(self,question,documents,source_ids=None):
                documents=set(documents)&GOLD
                if not documents or source_ids==[]:return {'publication_id':None,'revision':None,'rows':[],'embedding_calls':0,'truncated':False}
                key=hashlib.sha256(json.dumps([question,sorted(documents),source_ids],ensure_ascii=False).encode()).hexdigest()
                if key in self.cache:return self.cache[key]
                begin=time.monotonic();r=requests.post('http://127.0.0.1:%d/v1/embeddings'%port,json={'model':'BAAI/bge-m3','input':[question]},timeout=60);r.raise_for_status()
                vector=iv.normalize(r.json()['data'][0]['embedding'],1024);self.calls+=1
                embeds.append({'stage':stages[-1] if stages else 'request','seconds':round(time.monotonic()-begin,3),'chars':len(question)})
                cur=oracle.cursor();begin=time.monotonic()
                cur.execute(f"SELECT RGLT_DOC_ID,BODY_UNIT_ID,MIN(VECTOR_DISTANCE(EMBD_VCTR,TO_VECTOR(:v),COSINE)) AS D FROM {OWNER}.IDD_B003_LGL_VCTR_ITEM WHERE VCTR_POST_ID=:p AND RGLT_DOC_ID IN (SELECT j.did FROM JSON_TABLE(:docs,'$[*]' COLUMNS(did VARCHAR2(100) PATH '$')) j) GROUP BY RGLT_DOC_ID,BODY_UNIT_ID ORDER BY D,RGLT_DOC_ID,BODY_UNIT_ID FETCH FIRST 150 ROWS ONLY",
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
            if '_adr_vector' not in self.__dict__:self.__dict__['_adr_vector']=GoldVectorRetriever(self)
            return self.__dict__['_adr_vector']
        nm.ReverseMatcher.initial_vector=property(_initial_vector)
    audited=ExperimentClient(ROOT,base/'experiment-client',max_calls=limits['per_request'],max_repairs=0,provider_policy=DES/'provider-policy.json')
    fallback,fallback_hash=load_fallback(DES/'fallback-policy.json')
    def send(*,body,ticket):
        assert MODE=='live','preflight never sends'
        if (base/'STOP_EXTERNAL.json').exists() or (ART/'STOP_ALL.json').exists():raise errors.ContractError('Previous unknown: external sending stopped')
        allcalls=[c for p in (ART/'live').glob('*/*/calls.json') for c in read(p)]
        if len(allcalls)>=limits['physical_total'] or sum((c.get('usage') or {}).get('cost',0) for c in allcalls)>=limits['reported_cost_usd']:
            raise errors.BudgetExhausted('Frozen experiment total budget')
        verify_loaded(ART/'transport')
        # ADR-1519 (user 2026-11-12): a provider that gives no usable answer is replaced by the next pre-checked one
        # for the same request (design/fallback-policy.json); the cell stops only when every provider failed.
        try:
            return send_with_fallback(audited,body=body,ticket=ticket,phase=stages[-1] if stages else 'request',error_module=errors,
                request_encoder=local.provider_request,policy=fallback,policy_sha256=fallback_hash,recorder=record)
        except errors.TransportError as exc:
            if getattr(exc,'code',None)=='MODEL_PROVIDERS_EXHAUSTED':
                put(base/'STOP_EXTERNAL.json',{'reason':'every fallback provider failed','attempts':(exc.response or {}).get('fallback_attempts'),'no_automatic_retry':True})
            raise
    def record(event,row,extra):
        if event=='started':
            guard.check();payload=extra
            assert payload['model']=='qwen/qwen3.8-27b' and payload['reasoning']=={'effort':'none'} and payload['stream'] is True
            assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
            n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
            calls.append({'number':n,'stage':stages[-1] if stages else None,'canonical_number':len(generations),'status':'started',
                          'provider':payload['provider'],'provider_name':row['provider'],'fallback_index':row['provider_index'],
                          'request_chars':len(json.dumps(payload,ensure_ascii=False))})
            put(base/'calls.json',calls);gz(out/'request.json.gz',payload)
            print('MODEL',case_id,n,calls[-1]['stage'],row['provider'],flush=True)
        else:
            c=calls[-1];failure=row.get('failure')
            c.update(status='responded' if failure is None else 'switched',failure=failure,http_status=row.get('http_status'),usage=row.get('usage'),
                     actual_provider=row['provider'] if failure is None else None,finish_reason=row.get('finish_reason'),
                     blank=failure in ('BLANK_STALL','NO_NONBLANK','EMPTY_ANSWER'),seconds=row.get('seconds'),
                     first_nonblank_s=row.get('first_nonblank_s'),detail=row.get('detail'))
            put(base/'raw'/f"call-{c['number']:03d}"/'finished.json',c);put(base/'calls.json',calls)
    t.send_once=send
    original_post=request_deadline.post_json
    def post(url,**kw):
        guard.check();payload=kw['json_body'];assert payload['model']=='qwen/qwen3.8-27b' and payload['reasoning']=={'effort':'none'}
        assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
        n=len(calls)+1;out=base/'raw'/f'call-{n:03d}';out.mkdir(parents=True,exist_ok=False)
        row={'number':n,'stage':stages[-1] if stages else None,'canonical_number':len(generations),'status':'started','provider':payload['provider'],'request_chars':len(json.dumps(payload,ensure_ascii=False))}
        calls.append(row);put(base/'calls.json',calls);gz(out/'request.json.gz',payload);begin=time.monotonic()
        print('MODEL',case_id,n,row['stage'],flush=True)
        try:
            response=original_post(url,**kw)
            try:value=response.json()
            except ValueError:value={'non_json':response.text}
            gz(out/'response.json.gz',value)
            choice=((value.get('choices') or [{}])[0] or {}) if isinstance(value,dict) else {}
            content=((choice.get('message') or {}).get('content')) if isinstance(choice,dict) else None
            row.update(status='unknown' if response.status_code>=500 else 'responded',http_status=response.status_code,usage=value.get('usage'),
                       actual_provider=value.get('provider'),actual_model=value.get('model'),finish_reason=choice.get('finish_reason'),
                       blank=(response.status_code==200 and not (content or '').strip()),transport_diagnostics=response.extensions.get('absolute_deadline',{}))
            if row['status']=='unknown':put(base/'STOP_EXTERNAL.json',{'call':n,'reason':'remote5xx'})
            return response
        except Exception as exc:
            row.update(status='unknown',error_type=type(exc).__name__,error=str(exc)[:300],transport_diagnostics=getattr(exc,'diagnostics',{}))
            if hasattr(exc,'partial_body'):gz(out/'partial.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode(),'diagnostics':getattr(exc,'diagnostics',{})})
            put(base/'STOP_EXTERNAL.json',{'call':n,'reason':'Unknown physical outcome','no_automatic_retry':True});raise
        finally:
            row['seconds']=round(time.monotonic()-begin,3);put(out/'finished.json',row);put(base/'calls.json',calls)
    request_deadline.post_json=post
    original_generate=gateway.ModelGateway.generate
    def generate(self,phase,view,schema_name,**kwargs):
        n=len(generations)+1;stage=view.get('source_stage',phase);row={'number':n,'stage':stage};generations.append(row);stages.append(stage)
        gz(base/'canonical'/f'{n:03d}.json.gz',{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name) if isinstance(schema_name,str) else schema_name})
        begin=time.monotonic()
        try:
            v=original_generate(self,phase,view,schema_name,**kwargs);gz(base/'canonical'/f'{n:03d}-output.json.gz',v);row['status']='accepted';return v
        except Exception as exc:row.update(status='rejected',error_type=type(exc).__name__,error=str(exc)[:500]);raise
        finally:stages.pop();row['seconds']=round(time.monotonic()-begin,3);put(base/'generations.json',generations)
    gateway.ModelGateway.generate=generate
    loaded={n:Path(m.__file__).resolve() for n,m in list(sys.modules.items()) if n.split('.')[0] in ('semantic_runtime',package) and getattr(m,'__file__',None)}
    offenders=sorted(str(v) for v in loaded.values() if not (v.is_relative_to(C.resolve()) and files.get(str(v.relative_to(C.resolve())))==sha(v)))
    assert loaded and not offenders,('every loaded product module must equal the release bytes',offenders[:8])
    views=importlib.import_module(package+'.chat_adapter').views()
    sid='adr'+TARGET+'-'+ARM+'-'+case_id+('-rerun' if RERUN else '')
    body=views._request_body(case['question'],{'applied_fields':{'mode':case['mode']},'team_id':case['team'],'session_id':sid,'request_id':sid+'-1',
                                                'document_ids':sorted(allowed),'memory':True,'public_question':True,'use_llm':True})
    body['public_question']=True
    assert body['question'].startswith(case['mode']+':'),body['question']
    put(base/'binding.json',{'arm':ARM,'flow':code['flow'],'case':{k:case[k] for k in ('id','kind','generation','team','mode','vector')},'scope_documents':len(allowed),'projected_team_documents':len(missing),
        'loaded_product_modules':len(loaded),'code_root':str(C.relative_to(ROOT)),'release_id':code['release_id'],'profile':agent.profile,'root_binding':entry._BINDING,
        'generation':gspec,'initial_search':os.environ['GENOS_RAG_INITIAL_SEARCH'],'ld_preload':os.environ.get('LD_PRELOAD'),'vector':'Oracle Gold items via local bge-m3' if case['vector'] else 'none (body search fallback)'})
    health=asyncio.run(entry.service({},{'API_TYPE':'HEALTH'}));assert health['status']==200,health
    guard.rebase()
    if MODE=='preflight':
        put(base/'result.json',{'ready':True,'model_calls':0,'http_health':200,'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss});print('PREFLIGHT_READY',case_id,flush=True)
    else:
        turn=base/'turn-1';turn.mkdir();put(turn/'request.json',{**body,'document_ids':'%d documents'%len(body['document_ids'])})
        r0=resource.getrusage(resource.RUSAGE_SELF);begin=time.monotonic()
        response=asyncio.run(entry.service({},deepcopy(body)));elapsed=time.monotonic()-begin;r1=resource.getrusage(resource.RUSAGE_SELF)
        value=response.get('body') or {};gz(turn/'response.json.gz',{'http_status':response['status'],'body':value})
        answer=value.get('answer') or {};text=answer.get('text','') if isinstance(answer,dict) else str(answer);(turn/'answer.txt').write_text(text)
        term=((value.get('assembly') or {}).get('term_agent') or {});reply=term.get('guided_reply') or {}
        model_seconds=sum(c.get('seconds') or 0 for c in calls)
        result={'case_id':case_id,'kind':case['kind'],'http_status':response['status'],'request_seconds':round(elapsed,3),'model_seconds':round(model_seconds,3),
            'non_model_seconds':round(elapsed-model_seconds,3),'cpu_seconds':round((r1.ru_utime-r0.ru_utime)+(r1.ru_stime-r0.ru_stime),3),
            'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),'blank':sum(bool(c.get('blank')) for c in calls),
            'http429':sum(c.get('http_status')==429 for c in calls),'generations':len(generations),'rejected_generations':sum(g.get('status')=='rejected' for g in generations),
            'status':value.get('status'),'method':value.get('method_id'),
            'error_code':value.get('error_code') or ((value.get('error') or {}).get('code') if isinstance(value.get('error'),dict) else value.get('error')),
            'message':str(value.get('message') or value.get('detail') or '')[:400],
            'claims':len(answer.get('claims',[])) if isinstance(answer,dict) else 0,'answer_chars':len(text),
            'needs_guidance':reply.get('needs_guidance'),'accepted_outcome':term.get('accepted_outcome'),
            'embedding_calls':len(embeds),'vector_sql':vector_sql}
        if case['kind']=='compare':
            result['sides']={s:{'status':r.get('status'),'evidence':len(r.get('evidence_ids',[])),'error_code':r.get('error_code')} for s,r in (value.get('rag_results') or {}).items()}
            result['comparison_items']=len((value.get('comparison_items') or {}).get('items',[])) if isinstance(value.get('comparison_items'),dict) else None
            table=value.get('comparison_table') or {}
            src=lambda rows:[{'document':s.get('document_name'),'heading':s.get('coordinate_label')} for s in rows or []]
            result['table']={'rows':[{'label':r.get('label'),'internal':src(r.get('internal')),'external':src(r.get('external')),
                                      'verdicts':[o.get('verdict_label') for o in r.get('opinions',[])],'unresolved':len(r.get('unresolved',[])),
                                      'placement':r.get('placement')} for r in table.get('rows',[])],
                             'final_answer_rows':len(table.get('final_answer',[]) or []),
                             'unreviewed':[{'side':s.get('side'),'document':s.get('document_name'),'heading':s.get('coordinate_label')} for s in table.get('unreviewed_originals',[])]}
            result['failure_points']=[{k:p.get(k) for k in ('no','kind','stage','title','target')} for p in value.get('failure_points',[]) or []]
            result['questions']={s:r.get('question') for s,r in (value.get('rag_results') or {}).items()}
            result['concepts']=[{k:c.get(k) for k in ('label','pair_status')} for c in ((value.get('concept_plan') or {}).get('concepts') or [])]
            # r7: pairing packets left out after correction, and how many of their rows were kept.
            result['pair_skips']=[{'reason':p.get('reason'),'evidence':len(p.get('evidence_ids',[])),'kept_rows':p.get('kept_rows')}
                                  for p in ((value.get('concept_plan') or {}).get('skipped_packets') or [])]
        if response['status']==200:
            (turn/'public-answer.txt').write_text(views._public_answer_text(value));count=len(calls);g0=len(generations)
            again=asyncio.run(entry.service({},deepcopy(body)))
            result['duplicate']={'http_status':again['status'],'same_answer':(again.get('body') or {}).get('answer')==value.get('answer'),'extra_model_calls':len(calls)-count,'extra_generations':len(generations)-g0}
        put(turn/'result.json',result);put(base/'result.json',{'case_id':case_id,'turns':[result],'physical_calls':len(calls),'unknown':result['unknown']})
        print('LIVE_RESULT',json.dumps({k:result[k] for k in ('case_id','http_status','request_seconds','model_seconds','cpu_seconds','physical_calls','unknown','claims','status')},ensure_ascii=False),flush=True)
    try:entry.request_report._FINALIZER_QUEUE.join()
    except Exception:pass
except Exception as exc:
    put(base/'runner-failure.json',{'error_type':type(exc).__name__,'error':str(exc)[:2000],'traceback':traceback.format_exc(),'model_calls':len(calls)});raise
finally:
    if app is not None:
        try:app.state.pipeline.store.close()
        except Exception:pass
    if MODE=='live':guard.done.set();guard.thread.join(2)
    put(base/'resource-final.json',{'peak_rss_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'code_unchanged':code_unchanged(),
        'embedding_calls':len(embeds),'vector_sql_calls':len(vector_sql),'oracle_driver_loaded':'oracledb' in sys.modules})
