"""Native API E2E, explicit public research host, serial and no answer caching."""
from common import *
from contextlib import contextmanager
from copy import deepcopy
import argparse,gzip,importlib,os,re,sqlite3,sys,time,traceback
sys.dont_write_bytecode=True

class LabDB:
    def __init__(self,path):
        self.raw=sqlite3.connect(path,isolation_level=None,check_same_thread=False);self.raw.row_factory=sqlite3.Row
    def execute(self,sql,args=()):return self.raw.execute(re.sub(r'FETCH FIRST (\d+) ROWS ONLY',r'LIMIT \1',sql),args)
    @contextmanager
    def transaction(self):
        self.raw.execute('BEGIN IMMEDIATE')
        try:yield;self.raw.commit()
        except BaseException:self.raw.rollback();raise

def setup(directory,preflight=False):
    meta=read(DES/'candidate.json');P=ROOT/meta['path']
    if preflight:S=P/'snapshot'
    else:
        freeze=read(DES/'freeze.json')
        for n,h in freeze['files'].items():assert sha(ROOT/n)==h,n
        cm=read(P/'candidate.json');revision=cm['revisions'][-1]
        assert revision['revision_sha256']==freeze['revision_sha256']
        for f in revision['files']:assert sha(ROOT/f['frozen_path'])==f['snapshot_sha256']
        S=P/'revisions'/revision['revision_id']/'snapshot'
    C=S/meta['selected_code_relative'];selected=read(DES/'selected.json')
    os.environ.update(GENOS_RESIDENT_DATA='off',GENOS_AUTO_WARMUP='0',AD_WORKER_ENABLED='0',LAWRAG_WORKSPACE_ROOT=str(ROOT),MALLOC_ARENA_MAX='1')
    sys.path[:0]=[str(C/'02_BACKEND'),str(S/'02_BACKEND'),str(ROOT)]
    import lawrag,lawrag.pipeline
    lawrag.__path__.append(str(S/'02_BACKEND/lawrag'))
    lawrag.pipeline.__path__.append(str(S/'02_BACKEND/lawrag/pipeline'))
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.local_gemma import LocalQwen38Transport
    from lawrag.legal_knowledge.adapters.oracle import ddl
    from lawrag.legal_knowledge.adapters.repository import Repository
    from lawrag.legal_knowledge.adapters.existing import ExistingReferences
    from lawrag.legal_knowledge.application import Service
    from lawrag.legal_knowledge.contracts import digest
    directory.mkdir(parents=True,exist_ok=True);gold=directory/'gold_layer';gold.mkdir(exist_ok=True)
    db_path=gold/'knowledge.sqlite'
    db=LabDB(db_path);db.raw.executescript(ddl({n:n for n in ('lk_record','lk_head','lk_lookup')}));db.raw.close()
    t=LocalQwen38Transport(C,ROOT);holder={}
    who={'authenticated':True,'tenant_id':'cm-e2e','team_id':'financial_team','user_id':'cm-curator',
         'document_ids':sorted(t.public_scope),'knowledge_roles':['read','edit','publish']}
    @contextmanager
    def factory():
        db=LabDB(db_path)
        try:yield Service(Repository(db),ExistingReferences(holder['app'].state.pipeline.store))
        finally:db.raw.close()
    profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile.update(model_binding=t.binding,max_concurrent_requests_per_process=1,max_model_attempts=24,wall_seconds=900,max_transport_retries=0)
    app=create_app(directory,ROOT/selected['release']['data_path'],contracts_root=C,workspace_root=ROOT,
      runtime_root=directory/'agent_layer/runtime',provider=object(),vector=False,
      implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=t,
      memory_identity=lambda request:dict(who),knowledge_factory=factory,knowledge_identity=lambda request:dict(who),
      release={'mode':'isolated-e2e','release_id':'ADR0993','source_main':100,'storage':'LOCAL_RESEARCH_SQLITE_NOT_ORACLE'})
    holder['app']=app
    from semantic_runtime.stage_runner import StageRunner
    assert StageRunner(app.state.pipeline).verify_profile()
    from semantic_runtime.team_scope import select_documents
    who['document_ids']=sorted(set(who['document_ids'])&set(select_documents(app.state.pipeline.store,who['team_id'])))
    index=app.state.pipeline.term_agent.unit_fulltext
    binding={'generation':app.state.pipeline.store.manifest['generation_id'],'store_sha256':app.state.pipeline.store.manifest['store_sha256'],
             'unit_index_sha256':index.manifest['index_sha256'] if index else None}
    app.state.lab={'who':who,'binding':binding,'t':t,'gold':gold,'factory':factory,'directory':directory,'C':C}
    return app

def api(client,path,body=None):
    result=client.get(path) if body is None else client.post(path,json=body,headers={'X-Knowledge-Request':'1'})
    assert result.status_code==200,(path,result.status_code,result.text[:1800])
    return result.json()

def seed(app,client):
    from lawrag.legal_knowledge.application import ref
    from lawrag.legal_knowledge.contracts import digest,require
    from lawrag.legal_knowledge.ontology import evaluate
    from lawrag.pipeline.shortcut_package import import_package,verify_package,text_sha
    from lawrag.pipeline.legal_wiki_compiler import rebuild
    from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
    lab=app.state.lab;gold=lab['gold'];store=app.state.pipeline.store;who=lab['who'];binding=lab['binding']
    curated=read(DES/'curated-source-values.json');sources={s['id']:s for s in curated['sources']};templates=read(DES/'method-templates.json')
    concepts={'underwriting':'공동주관 보유비율과 보유제외','counting':'증권별 보유수 산정','listing':'상장주선인 의무인수와 보유기간','listing_detail':'취득방법 및 연장 사유 구체화'}
    package={'schema_version':'curated-source-package-v1','package_id':'ADR0993-counterfactual-correction','legal_claim_reuse':False,'cases':[]}
    notes={}
    for sid in sources:
        entries=[]
        for sid in [sid]:
            s=sources[sid];require(s['source_metadata']['security_class']=='public' and s['source_metadata']['export_allowed'],'EXPORT','not public')
            for block in s['blocks']:
                raw=store.source(s['document_id'],block['id']);assert text_sha(raw['text'])==block['sha256']
            text='\n'.join(b['text'] for b in store.section(s['document_id'],s['node'])['blocks'])
            doc=store.db.execute('SELECT name,source_artifact_sha256 FROM document WHERE document_id=?',(s['document_id'],)).fetchone()
            assert doc['source_artifact_sha256']==s['source_artifact_sha256']
            entries.append({'document_id':s['document_id'],'document_name':doc['name'],'source_artifact_sha256':s['source_artifact_sha256'],
                'article_root_unit_id':s['node'],'coordinate_key':s['coordinate_key'],'section_text_sha256':text_sha(text),
                'article':s['article'],'evidence_role':'source_anchor'})
        key='source:'+s['document_id']+':'+s['node']
        notes[sid]={'id':key,'primary_key':{'document_version_id':s['document_id'],'coordinate_key':s['coordinate_key'],'concept':concepts[sid]},
            'source_checks':[c for p in curated['packs'] for c in p['checks'] if c['evidence_binding']['source_id']==sid],
            'provenance_experiences':[p['seed'] for p in curated['packs'] if sid in p['evidence_sources']],
            'origin':'SOURCE_BOUND_CURATED_ANNOTATION','legal_approval':False}
        package['cases'].append({'case_id':key,'question':s['title']+' '+s['article']+' — '+concepts[sid],
            'topic':concepts[sid],'entries':entries,
            'reference_answer':json.dumps(notes[sid],ensure_ascii=False),
            'reference_provenance':{'kind':'COUNTERFACTUAL_SOURCE_CURATED_CORRECTION','experience_file':str((ART/'agent_layer/corrected-experiences.json').relative_to(ROOT)),
                'experience_sha256':sha(ART/'agent_layer/corrected-experiences.json')}})
    put(gold/'source-package.json',package)
    repo=ShortcutRepository(gold/'wiki.sqlite')
    imported=import_package(repo,who,package,store);projection=rebuild(repo,who,gold/'llm_wiki')
    assert len(imported['records'])==4 and projection['pages']==4
    def command(op,args,key):return api(client,'/v1/legal-knowledge/commands',{'schema_version':'legal-knowledge-v1','operation':op,'operation_id':'ADR0993:'+key,'arguments':args})
    records=[];routes={};definitions=[];source_records={}
    for sid,note in notes.items():
        s=sources[sid];d=deepcopy(templates[0]['definition'])
        d.update(title=s['title']+' '+s['article']+' · '+concepts[sid],
            description='원문 중심 저장 단위 '+note['id']+'. 이 조문과 개념에 도달하면 아래 사항과 연결 원문을 확인한다. 질문은 발견 이력일 뿐 저장 키가 아니다.',lookup_terms=[])
        refs=[]
        for check in note['source_checks']:
            for bid in check['evidence_binding']['block_ids']:
                block=next(b for b in s['blocks'] if b['id']==bid)
                r={'document_id':s['document_id'],'version':s['document_id'],'locator':bid,'content_hash':block['sha256']}
                if r not in refs:refs.append(r)
        d['source_refs']=refs
        labels=[c['id']+': '+json.dumps(c['value'],ensure_ascii=False,separators=(',',':')) for c in note['source_checks']]
        d['content']={'purpose':concepts[sid],'requested_outputs':['현재 질문과 관련된 검토 사항'],'inputs':[],
           'evidence_needs':[s['title']+' '+s['article']],
           'steps':[{'id':'source-check-'+str(i),'label':label,'capability':'READ_SOURCE','after':[]} for i,label in enumerate(labels)],'policies':[]}
        r=command('save_draft',{'object_id':None,'expected_revision':0,'definition':d},note['id']);records.append(r);definitions.append(d);source_records[sid]=r
        routes[r['id']]=next(x for x in imported['records'] if x['case_id']==note['id'])
        note['ontology_ref']=ref(r);note['wiki_ref']=routes[r['id']]
    abstract=[]
    for item in templates:
        d=deepcopy(item['definition'])
        pack=next(p for p in curated['packs'] if p['id']==item['key'])
        d['dependencies']=[ref(source_records[sid]) for sid in pack['evidence_sources']]
        d['content']['steps']=[{'id':'inspect-source-concepts','label':'관련 원문의 개념별 검토 사항과 연결 근거를 확인한다. 현재 질문의 적용성을 판단한다.','capability':'READ_SOURCE','after':[]}]
        d['source_refs']=[]
        for source in d['source_refs']:
            got=api(client,'/v1/legal-knowledge/source-reference',{k:source[k] for k in ('document_id','locator')});assert got['ref']==source
        r=command('save_draft',{'object_id':None,'expected_revision':0,'definition':d},item['key']);records.append(r);definitions.append(d);abstract.append(r)
    # An actual typed AND expression, with explicit missing facts rather than a guessed result.
    fields=[]
    for i,title in enumerate(['현재 상장신청인의 혁신기술기업 해당','주선인의 세칙 제15조제5항 사유 해당']):
        d=deepcopy(templates[1]['definition']);d.update(kind='FIELD',title=title,description=title+' 여부는 현재 사건 사실과 원문으로 별도 판단한다.',lookup_terms=[])
        d['content']={'value_type':'boolean','dimension':'법률 적용 요건','legal_purpose':'일반 국내3개월 보유의6개월 연장','concept_refs':[], 'allowed_origins':['USER','SOURCE','MODEL_PROPOSAL']}
        r=command('save_draft',{'object_id':None,'expected_revision':0,'definition':d},'field-'+str(i));fields.append(ref(r));records.append(r);definitions.append(d)
    d=deepcopy(templates[1]['definition']);d.update(kind='APPLICATION',title='일반 국내기업 보유기간6개월 연장 조건',lookup_terms=['3개월','6개월'],
       description='현재 혁신기술기업 AND 주선인의 세칙 사유가 모두 필요하다. 세칙 사유는 최근3년 내 주선한 기술성장기업의 상장 이후2년 내 지정·폐지 사유다.')
    d['content']={'method_refs':[ref(abstract[1])],'wiki_refs':[],'condition':{'op':'all','args':[{'field':f['id']} for f in fields]},'input_refs':fields,'requested_outputs':['두 요건의 충족 여부와6개월 연장 적용성']}
    r=command('save_draft',{'object_id':None,'expected_revision':0,'definition':d},'extension');records.append(r);definitions.append(d)
    build=command('prepare_publication',{'refs':[ref(r) for r in records],'source_binding':binding,'review_note':'사용자 요청에 따른 공개 원문 기반 가정 성공 경험. Codex 작성, 전문가 승인 없음, 연구용으로만 게시.'},'prepare')
    publication=command('publish',{'build_id':build['id'],'build_hash':build['content_hash'],'expected_revision':0},'publish')
    put(gold/'method-route-bindings.json',routes)
    put(gold/'source-concept-registry.json',list(notes.values()))
    truth=[]
    for values in [(True,True),(True,False),(True,None),(False,True)]:
        facts={f['id']:{'status':'ASSERTED','origin_ref':'synthetic-contract-check','value':{'type':'boolean','value':v,'unit':''}} for f,v in zip(fields,values) if v is not None}
        result=evaluate(d['content']['condition'],facts,binding=binding);truth.append({'facts':values,'receipt':result})
    assert [x['receipt']['status'] for x in truth]==['TRUE','FALSE','UNKNOWN','FALSE']
    grant={'schema_version':'knowledge-export-grant-v1','principal':{k:who[k] for k in ('tenant_id','team_id','user_id')},
        'source_binding':binding,'question_hashes':[digest(c['question']) for c in read(DES/'cases.json')],
        'definition_hashes':[digest(d) for d in definitions]}
    lab['t'].knowledge_export_grant=grant
    # New research glue only: approved-public source paths from the existing authority
    # feed existing discovery. It cannot insert claims, facts or a completed answer.
    def bind_route(plan,principal,question,source_binding):
        require(source_binding==binding,'KNOWLEDGE_SOURCE_BINDING','binding drift',409)
        targets=[];origins=[]
        with context_repo(gold/'wiki.sqlite') as current:
            for item in plan['items']:
                record=routes.get(item['ref']['id'])
                if record is None:continue
                value=current.current(record['unit_id'],record['revision'],principal)
                require(value['hash']==record['hash'] and set(value['documents'])<=set(lab['t'].public_scope),'KNOWLEDGE_INTEGRITY','route hash or scope',409)
                path=value['core_evidence_route'];require(path['source_binding']==binding,'KNOWLEDGE_SOURCE_BINDING','route binding',409)
                for target in path['targets']:
                    require(target['document_id'] in principal['document_ids'],'KNOWLEDGE_NOT_FOUND','source denied',404)
                    if target not in targets:targets.append(deepcopy(target))
                origins.append({'method':item['ref'],'wiki_unit':record['unit_id'],'wiki_revision':record['revision'],'wiki_hash':record['hash']})
        if not targets:return None
        return {'unit_id':'knowledge-route:'+digest(origins),'revision':1,'goal_revision':None,'targets':targets,'origins':origins,
                'source_binding':binding,'legal_claim_reuse':False}
    lab['t'].knowledge_source_route=bind_route
    previews=[{'id':c['id'],'plan':api(client,'/v1/legal-knowledge/preview',{'query':c['question'],'source_binding':binding})} for c in read(DES/'cases.json')]
    assert all(x['plan']['items'] for x in previews)
    checks=[]
    with lab['factory']() as service:
        assert not service.plan(who,'근로자의 연차휴가',binding)['items'];checks.append('unrelated query miss')
        stale=service.plan(who,'보유비율',{**binding,'generation':'stale'})
        assert not stale['items'] and 'SOURCE_BINDING_CHANGED' in stale['unresolved'];checks.append('stale generation rejected')
        denied=service.plan({**who,'document_ids':[]},'보유비율',binding)
        assert not denied['items'];checks.append('document ACL rejected')
        from lawrag.legal_knowledge.contracts import KnowledgeError
        try:service.references.verify_source({**templates[0]['definition']['source_refs'][0],'content_hash':'0'*64},who,binding)
        except KnowledgeError as exc:assert exc.code=='KNOWLEDGE_SOURCE_HASH';checks.append('changed source hash rejected')
        else:raise AssertionError('tampered source accepted')
    for preview in previews:
        route=bind_route(preview['plan'],who,next(c['question'] for c in read(DES/'cases.json') if c['id']==preview['id']),binding)
        assert route and all(t['document_id'] in who['document_ids'] for t in route['targets'])
    checks.append('all4 plans resolve source-based routes')
    assert command('publish',{'build_id':build['id'],'build_hash':build['content_hash'],'expected_revision':0},'publish')==publication
    checks.append('duplicate publication idempotent')
    assert {r['case_id'] for r in imported['records']}=={v['id'] for v in notes.values()}
    assert not any(r['case_id'].startswith('cm-') for r in imported['records']);checks.append('primary wiki key is source coordinate not question')
    receipt={'import':imported,'wiki_projection':projection,'records':records,'build':build,'publication':publication,
             'previews':previews,'condition_checks':truth,'contract_checks':checks,'source_binding':binding,'native_success_forged':False,'expert_approved':False,'oracle_executed':False}
    put(gold/'publication-receipt.json',receipt);put(gold/'export-grant.json',grant);repo.close()
    return receipt

@contextmanager
def context_repo(path):
    from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
    r=ShortcutRepository(path)
    try:yield r
    finally:r.close()

def run(app,client):
    from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError,ExperimentTransportError
    from semantic_runtime.legal_agent.local_gemma import provider_request
    from semantic_runtime.legal_agent import errors,gateway
    from semantic_runtime.legal_agent.model_contract import structured_content
    lab=app.state.lab;t=lab['t'];cases={c['id']:c for c in read(DES/'cases.json')};results=[];current={}
    original=gateway.ModelGateway.generate
    def generate(self,phase,view,schema_name,**kwargs):
        row={'number':len(current['generations'])+1,'phase':phase,'schema_name':schema_name};current['generations'].append(row)
        gz(current['out']/'canonical'/f"{row['number']:03d}.json.gz",{'phase':phase,'view':view,'schema':self.protocol.schema(schema_name)})
        try:
            value=original(self,phase,view,schema_name,**kwargs);row['accepted']=True;gz(current['out']/'canonical'/f"{row['number']:03d}-output.json.gz",value);return value
        except BaseException as exc:row.update(accepted=False,error_type=type(exc).__name__,error=str(exc));raise
        finally:put(current['out']/'generations.json',current['generations'])
    gateway.ModelGateway.generate=generate
    def send_once(*,body,ticket):
        assert not current.get('provider_failed'), 'Provider failed: no further dispatch'
        calls=current['client'];n=calls.calls+1;out=current['out'];phase=current['generations'][-1]['phase'] if current['generations'] else 'native'
        assert body['model']==t.binding['model'];gz(out/'wire'/f'{n:03d}.json.gz',body)
        row={'call':n,'phase':phase,'status':'started'};current['calls'].append(row);put(out/'calls.json',current['calls'])
        print('MODEL',current['id'],current['arm'],n,phase,flush=True);started=time.monotonic()
        try:
            try:raw=calls.chat_completions(provider_request(body),phase=phase,timeout_seconds=min(180,ticket['remaining_seconds']))
            except ExperimentFormatError as exc:
                if exc.response:
                    try:structured_content(exc.response['body_json'],require_complete=True)
                    except Exception as cause:cause.response=exc.response;raise
                err=errors.ProposalError('Incomplete external response');err.response=exc.response;raise err from exc
            except ExperimentProviderError as exc:
                current['provider_failed']=True
                status=(exc.response or {}).get('status_code',0)
                if status==200:raise errors.ContractError('Actual provider/model mismatch') from exc
                raise errors.TransportError('External request failed',retryable=False,unknown=False,response=exc.response) from exc
            except ExperimentTransportError as exc:
                current['provider_failed']=True
                raise errors.TransportError(str(exc),retryable=exc.retryable,unknown=exc.unknown) from exc
            assert raw['body_json']['model']==t.binding['model'] and raw['body_json']['provider']=='Parasail'
            raw['acceptance']='ACCEPTED';row.update(status='completed',http_status=raw['status_code']);return raw
        except BaseException as exc:row.update(status='failed',error_type=type(exc).__name__,error=str(exc));raise
        finally:row['seconds']=time.monotonic()-started;put(out/'calls.json',current['calls'])
    t.send_once=send_once
    config=app.state.pipeline.contracts.pipeline['legal_knowledge']
    for cid,arm in read(DES/'criteria.json')['order']:
        out=RUN/'agent_layer'/arm/cid
        if out.exists():raise RuntimeError('Started request preserved; no automatic replay')
        out.mkdir(parents=True);case=cases[cid];config['consumer_mode']='consume';app.state.pipeline.term_agent.transport.knowledge_delivery_enabled=(arm=='candidate')
        calls=ExperimentClient(ROOT,out/'raw',max_calls=24,max_output_tokens=app.state.pipeline.term_agent.profile['max_output_tokens'],max_repairs=0)
        current.clear();current.update(out=out,client=calls,id=cid,arm=arm,calls=[],generations=[])
        request={'question':case['question'],'document_ids':lab['who']['document_ids'],'public_question':True,'use_llm':True,
            'team_id':lab['who']['team_id'],'session_id':f'ADR0993-{cid}-{arm}','request_id':f'ADR0993:{cid}:{arm}'}
        put(out/'request.json',request);before={str(p) for p in (RUN/'agent_layer/runtime').rglob('journal.sqlite')};started=time.monotonic();fatal=False
        row={'case_id':cid,'arm':arm,'cohort':case.get('cohort'),'status':'STARTED','actual_native_api':True}
        try:
            response=client.post('/v1/rag/ask',json=request);value=response.json();put(out/'response.json',{'http_status':response.status_code,'body':value})
            answer=value.get('answer') or {};text=answer.get('text','') if isinstance(answer,dict) else str(answer)
            (out/'answer.txt').write_text(text)
            row.update(http_status=response.status_code,status=value.get('status'),has_answer=bool(text),error=value.get('detail') or value.get('error'))
            serialized=json.dumps(value)
            if 'INTERNAL_CONTRACT_ERROR' in serialized or (response.status_code>=400 and any(x in serialized for x in ['hash mismatch','INTEGRITY','IMPLEMENTATION_FAILURE','source outside','scope denied'])):fatal=True
        except BaseException as exc:
            row.update(status='EXCEPTION',error_type=type(exc).__name__,error=str(exc));(out/'error.txt').write_text(traceback.format_exc())
            fatal=isinstance(exc,(errors.ContractError,AssertionError,KeyboardInterrupt,MemoryError))
        finally:
            fatal=fatal or current.get('provider_failed',False)
            after={str(p) for p in (RUN/'agent_layer/runtime').rglob('journal.sqlite')}
            row.update(seconds=time.monotonic()-started,model_calls=calls.calls,usage=calls.usage,
                journal_paths=[str(Path(p).relative_to(ROOT)) for p in sorted(after-before)],fatal=fatal)
            put(out/'result.json',row);results.append(row);put(RUN/'result.json',{'results':results,'complete':len(results)==8,'fatal':fatal})
            print('DONE',cid,arm,row.get('http_status'),calls.calls,round(row['seconds'],2),flush=True)
        if fatal:break
        import gc,ctypes
        gc.collect();ctypes.CDLL(None).malloc_trim(0)

def gz(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'wt',encoding='utf8') as f:json.dump(value,f,ensure_ascii=False,separators=(',',':'))

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','run']);p.add_argument('--preflight-name',default='preflight');args=p.parse_args()
    directory=ART/args.preflight_name if args.action=='check' else RUN
    if directory.exists():raise RuntimeError('Preserve existing attempt; use explicit new preflight directory or new ADR for replay')
    app=setup(directory,args.action=='check')
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        receipt=seed(app,client);health=api(client,'/health');put(directory/'health.json',health)
        put(directory/'binding.json',{'source':app.state.lab['binding'],'code_root':str(app.state.lab['C'].relative_to(ROOT)),
          'profile':app.state.pipeline.term_agent.profile,'public_documents':app.state.lab['who']['document_ids'],
          'app_factory_injected':True,'native_api':'/v1/rag/ask','selected_main_modified':False})
        print('SEED PASS:4source wiki,4source METHOD+2abstract METHOD,2FIELD,1APPLICATION; public sources checked; AND truth table passed',flush=True)
        if args.action=='run':run(app,client)
        else:put(directory/'result.json',{'status':'PASS','model_calls':0,'wiki':4,'ontology_records':9,'and_checks':4})
    app.state.pipeline.store.close();sys.stdout.flush();os._exit(0)
if __name__=='__main__':main()
