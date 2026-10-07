"""Frozen paired Qwen3.8 request-routing probe. No gold is read by the product process."""
import argparse,hashlib,json,sys,time,traceback,subprocess
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0555-pecab-only-catalogue-routing'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
def pin(arm):
 design=read(ADR/'artifacts/frozen-design.json')
 for p,h in design['file_hashes'].items():
  if sha(ROOT/p)!=h:raise RuntimeError('Frozen input drift: '+p)
 code=ROOT/design['runtime_roots'][arm]
 sys.path[:0]=[str(code/'02_BACKEND'),str(ROOT/'02_BACKEND')]
 import importlib.util
 import lawrag
 lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
 import lawrag.research
 spec=importlib.util.spec_from_file_location('lawrag.research.experiment_client',ROOT/design['transport_path'])
 mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
 import semantic_runtime
 assert Path(semantic_runtime.__file__).is_relative_to(code)
 return {**design,'runtime_root':str(code.relative_to(ROOT))}
def run_one(case,arm,fixture,design,*,run_id="run-001",preflight=False):
    from semantic_runtime.storage import Store
    from semantic_runtime.pipeline import Pipeline
    from semantic_runtime.document_agent import ServingDocumentAgent
    from semantic_runtime.legal_agent.context import RequestContext
    from semantic_runtime.legal_agent.gateway import ModelGateway
    from semantic_runtime.contracts import digest
    from lawrag.research.experiment_client import ExperimentClient
    from lawrag.research.openrouter_legal_adapter import OpenRouterSingleSendAdapter
    from semantic_runtime.legal_agent import workflow_tiers_policy as policy,workflow_tiers_protocol as protocol
    from semantic_runtime.legal_agent.tiers_repository import TiersRepository as Repository
    from semantic_runtime.legal_agent.workflow_tiers_tools import TiersTools as Sources
    from semantic_runtime.legal_agent.tiers_session import TiersSession as Session
    out=ADR/'artifacts'/('preflight-001' if preflight else run_id)/case['case_id']/arm
    out.mkdir(parents=True,exist_ok=False)
    client=ExperimentClient(ROOT,out/'calls',max_calls=14,max_output_tokens=6400,scoped_policy_path=ADR/'artifacts/scoped-model-policy.json',scoped_policy_sha256=sha(ADR/'artifacts/scoped-model-policy.json'),max_repairs=0)
    if True:
        from semantic_runtime.legal_agent.obligation_repository import ObligationRepository as Repository
        from semantic_runtime.legal_agent.question_obligations import SYSTEM, PROMPTS
        from semantic_runtime.legal_agent.bounded_source_session import BoundedSourceSession as Session
        from semantic_runtime.legal_agent import obligation_protocol as protocol
    else: SYSTEM,PROMPTS=policy.SYSTEM,policy.PROMPTS
    wire=OpenRouterSingleSendAdapter(client);settings=policy.profile({**read(ROOT/design['runtime_root']/'00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json'),'model_binding':wire.binding,'question_obligations_enabled':True,'numbered_references_enabled':True,'wall_seconds':300,'max_schema_repairs':0,'max_transport_retries':0},require_model=True)
    started=time.monotonic();store=repo=session=sources=None
    row={'case_id':case['case_id'],'arm':arm,'error':None,'started_at':time.time(),'settings':settings,'preflight':preflight,'run_id':run_id,'publication_error':None}
    try:
        store=Store(ROOT/design['generations'][arm])
        assert store.manifest['store_sha256']==design['export_authorization']['source_store_sha256']
        p=Pipeline(ROOT/design['runtime_root'],store,implementation=policy.IMPLEMENTATION,legal_agent_profile=settings,legal_agent_transport=wire)
        query=p.plan(case['question'],fixture['public_scope_document_ids'])
        request={'question':case['question'],'document_ids':fixture['public_scope_document_ids'],'use_llm':True}
        agent=ServingDocumentAgent(p,p.term_agent.config)
        with agent.resources(query['scope']['document_version_ids']) as (index,tools,glossary,matcher):
            binding={'generation_id':store.manifest['generation_id'],'store_sha256':store.manifest['store_sha256'],
                'source_export_allowed':store.manifest['export_allowed'],'export_allowed':True,
                'export_authorization':design['export_authorization'],'scope':query['scope'],'model':wire.binding,
                'domain_sha256':digest(policy.DOMAIN),'profile_sha256':digest(settings),
                'pipeline_sha256':sha(ROOT/design['runtime_root']/'00_SYSTEM/PIPELINE.json'),
                'index_sha256':index.manifest['index_sha256'],'glossary':glossary.binding,
                'fulltext_sha256':matcher.fulltext.manifest['fulltext_sha256']}
            validate_export_authorization(binding)
            original_send=wire.send_once
            def authorized_send(*,body,ticket):
                validate_export_authorization(binding)
                return original_send(body=body,ticket=ticket)
            wire.send_once=authorized_send
            context=RequestContext.create(query,request,binding,settings['wall_seconds'])
            repo=Repository(out/'journal.sqlite',context,settings)
            sources=Sources(store,tools,glossary,matcher,repo,context,settings)
            gateway=ModelGateway(repo,context,settings,policy.DOMAIN,wire,message_protocol=protocol,system=SYSTEM,prompts=PROMPTS)
            session=Session(context,repo,sources,gateway,settings,store.manifest['data_status'])
            session.check_sources_unchanged=glossary.check_unchanged
            row.update(binding=binding,question_pieces=context.pieces)
            controller_started=time.monotonic()
            if preflight:
                view=session.view('investigate');row['preflight_view_keys']=list(view)
            else:
                retrieval=session.investigate()
                selected=session.select({'request':request,'query':query,'retrieval':retrieval})
                assembled={'request':request,'query':query,'retrieval':retrieval,'selection':selected,'assembly':session.assemble()}
                for _ in range(settings['max_cycles']+1):
                    result,control=session.answer_and_review(assembled)
                    if control['decision']=='FINAL':break
                    if control['decision']=='RESEARCH':
                        retrieval=session.investigate();selected=session.select({'retrieval':retrieval})
                        assembled={'request':request,'query':query,'retrieval':retrieval,'selection':selected,'assembly':session.assemble()}
                else:raise RuntimeError('Controller did not finalize')
                row.update(result=result,control=control,request_route=session.request_route,metadata_only=session.metadata_only,source_recall_summary={k:v for k,v in (session.source_recall_record or {}).items() if k not in ('evidence','packets','paths')})
                row['publication_status']='EXPERIMENT_RESULT';row['loaded_modules']={'session':__import__('inspect').getfile(Session),'policy':policy.__file__}
            row['controller_seconds']=round(time.monotonic()-controller_started,3)
            glossary.check_unchanged()
    except Exception as exc:
        row['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        if repo is not None:repo.fail(getattr(exc,'code',type(exc).__name__))
    finally:
        if repo is not None:
            evidence=repo.evidence();by_e={e['evidence_id']:e['source_id'] for e in evidence}
            handles=[dict(r) for r in repo.db.execute('SELECT * FROM navigation_handle')]
            discovered={json.loads(h['identity_json']).get('source_id') for h in handles}-{None}
            read_ids={e['source_id'] for e in evidence};discovered|=read_ids
            presented={by_e[r[0]] for r in repo.db.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'") if r[0] in by_e}
            packed=getattr(session,'packed',{}) or {};selected={by_e[e] for e in packed.get('evidence_ids',[]) if e in by_e}
            bundle=row.get('result',{}).get('assembly',{}).get('term_agent',{}).get('source_bundle',{})
            if True:
                selected={h['payload']['evidence_id'] for h in repo.heads('source_selection',current=True) if h['payload']['status']=='SELECTED'}
                selected={by_e[e] for e in selected}
            claims=repo.heads('claim',current=True)
            answer={sid for c in row.get('result',{}).get('answer',{}).get('claims',[]) for sid in c['source_ids']}
            payload_sources={c['source_id'] for c in bundle.get('sources',[])} if True else answer
            row.update(stages={k:sorted(v) for k,v in [('discovered',discovered),('read',read_ids),('presented',presented),('selected',selected),('answer',answer),('payload_sources',payload_sources),('final_sources',payload_sources if row.get('publication_status')=='PUBLISHED' else set())]},budget=repo.budget(),journal_run=repo.run(),limitations=getattr(session,'limitations',[]))
            trace={'handles':handles,'evidence':evidence,'assessments':repo.heads('assessment',current=True),
                'claims':claims,'observations':repo.observations(10000),'packed':packed,'errors':getattr(session,'errors',[]),'actions':[dict(x) for x in repo.db.execute('SELECT * FROM action_context')]}
            if True:
                trace['source_selections']=repo.heads('source_selection');trace['source_bundle']=bundle
            if True:
                trace.update(notices=repo.notices(),coverage=repo.coverage(),relation_assessments=repo.heads('relation_assessment',current=True))
            graph=getattr(session,'_protected_graph',None)
            if graph is not None:
                import gzip
                with gzip.open(out/'graph.json.gz','wt',encoding='utf-8') as f:json.dump(graph,f,ensure_ascii=False,separators=(',',':'))
                row['graph_summary']={k:graph.get(k) for k in ('status','seconds','policy')}
                row['graph_summary'].update(roots=len(graph['roots']),sources=len(graph['source_ids']),states=len(graph['states']),pending=len(graph['pending']))
                row['stages']['protected_originals']=graph['source_ids']
            else:row['stages']['protected_originals']=[]
            if bundle.get('reference_bundle'):
                bundle['reference_bundle']['graph_artifact']='graph.json.gz'
                bundle['reference_bundle'].pop('graph',None)
            import gzip
            with gzip.open(out/'trace.json.gz','wt',encoding='utf-8') as f:json.dump(trace,f,ensure_ascii=False,separators=(',',':'))
            if session is not None:
                write(out/'obligations.json',{'plan':session.plan(),'items':session.obligation_status(),'reviews':repo.heads('obligation_review',current=True)})
            repo.close()
        if store is not None:store.close()
        row.update(physical_calls=client.calls,usage=client.usage,seconds=round(time.monotonic()-started,3))
        write(out/'result.json',row)
    return row
def validate_export_authorization(binding):
    """Check current server-owned public-source grant, independently of immutable attributes."""
    from semantic_runtime.legal_agent.errors import ContractError
    import hashlib
    from lawrag.platform.workspace import load_layout
    grant=binding.get('export_authorization')
    if not grant: raise ContractError('external source grant required')
    layout=load_layout()
    auth_path=layout.path('deployment')/'CONFIG/legal-source-export.json'
    policy_path=layout.path('system')/'EXPERIMENT_MODEL_POLICY.json'
    # Explicit server-owned experiment grant; immutable source attributes stay intact.
    scoped=grant.get('experiment_policy_path')
    if scoped is not None:
        expected=layout.root/'04_EXPERIMENTS/ADR/ADR-0555-pecab-only-catalogue-routing/artifacts/scoped-model-policy.json'
        supplied=(layout.root/scoped).resolve()
        if supplied!=expected.resolve():raise ContractError('unexpected scoped experiment policy')
        candidate=json.loads(supplied.read_text())
        if (candidate.get('schema_version')!='user-authorized-openrouter-product-v2' or candidate.get('adr_id')!='ADR-0555'
            or candidate.get('model')!='qwen/qwen3.8-27b' or candidate.get('provider')!='openrouter'
            or candidate.get('authorization',{}).get('source')!='user_message'
            or candidate.get('source_scope')!=['public'] or candidate.get('main_wiring')!='unchanged'
            or candidate.get('fallback_allowed') is not False):raise ContractError('invalid scoped experiment grant')
        policy_path=supplied
    auth=json.loads(auth_path.read_text());policy=json.loads(policy_path.read_text())
    model=binding['model'];scope=set(binding['scope']['document_version_ids'])
    if (not auth.get('enabled') or sha(auth_path)!=grant.get('source_authorization_sha256') or
        sha(policy_path)!=grant.get('policy_sha256') or grant.get('model')!=policy['model'] or
        model['model']!=grant.get('model') or grant.get('destination')!=policy['endpoint'] or
        model['endpoint_identity']!=hashlib.sha256(policy['endpoint'].encode()).hexdigest() or
        grant.get('source_store_sha256')!=binding['store_sha256'] or
        grant.get('generation_id')!=binding['generation_id'] or
        grant.get('source_manifest_export_allowed')!=binding.get('source_export_allowed') or
        grant.get('public_questions_only') is not True or grant.get('private_documents_allowed') is not False or
        scope-set(grant.get('scope_document_ids',[])) or
        not any(scope<=set(b['document_version_ids']) for b in auth.get('bindings',[]))):
        raise ContractError('external source authorization stale or outside permitted scope/model/destination')


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--arm');parser.add_argument('--case');args=parser.parse_args()
 fixture=read(ADR/'product-cases.json')
 if args.arm:
  design=pin(args.arm);case=next(c for c in fixture['cases'] if c['case_id']==args.case)
  row=run_one(case,args.arm,fixture,design,preflight=not args.execute)
  print(json.dumps({'case':args.case,'arm':args.arm,'calls':row['physical_calls'],'seconds':row['seconds'],'error':row['error'] and row['error']['message'],'stages':{k:len(v) for k,v in row.get('stages',{}).items()},'graph':row.get('graph_summary')},ensure_ascii=False),flush=True)
  if row['error'] and not args.execute:raise SystemExit(1)
  return
 assert args.execute,'Specify --arm and --case for no-call preflight'
 from concurrent.futures import ThreadPoolExecutor,as_completed
 target=ADR/'artifacts/run-001';target.mkdir(exist_ok=False)
 results={'cases':{},'started_at':time.time(),'run_id':'run-001','arms':['baseline','catalogue-router']}
 def one(c,arm):
  logpath=target/(c['case_id']+'-'+arm+'.log')
  with logpath.open('w') as log:
   proc=subprocess.Popen([sys.executable,str(Path(__file__)),'--execute','--case',c['case_id'],'--arm',arm],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
   try:code=proc.wait(timeout=360);expired=False
   except subprocess.TimeoutExpired:proc.kill();code=proc.wait();expired=True
  out=target/c['case_id']/arm;p=out/'result.json'
  if not p.exists():
   calls=list((out/'calls').glob('call-*'));usage=read(out/'calls/usage.json') if (out/'calls/usage.json').exists() else []
   write(p,{'case_id':c['case_id'],'arm':arm,'error':{'type':'HardDeadlineExceeded' if expired else 'ChildProcessFailed','exit_code':code},'physical_calls':len(calls),'usage':usage,'seconds':360 if expired else None,'stages':{},'in_flight_usage_unknown':expired})
  row=read(p)
  return c['case_id'],arm,{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'error':row.get('error'),'calls':row['physical_calls'],'seconds':row['seconds'],'stages':{k:len(v) for k,v in row.get('stages',{}).items()},'graph':row.get('graph_summary')}
 with ThreadPoolExecutor(max_workers=3) as pool:
  jobs=[(c,a) for c in fixture['cases'] for a in (['baseline','catalogue-router'] if fixture['cases'].index(c)%2==0 else ['catalogue-router','baseline'])]
  for future in as_completed([pool.submit(one,c,a) for c,a in jobs]):
   cid,arm,row=future.result();results['cases'].setdefault(cid,{})[arm]=row;write(target/'results.partial.json',results)
   print(json.dumps({'case':cid,'arm':arm,**{k:v for k,v in row.items() if k not in ('path','sha256','error')},'error':row['error'] and row['error'].get('type')},ensure_ascii=False),flush=True)
 results['finished_at']=time.time();write(target/'results.json',results)
if __name__=='__main__':main()
