"""Bounded real-data service consumer; active mode never injects an app."""
from pathlib import Path
import asyncio,hashlib,importlib,importlib.util,json,os,sys,resource
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0961-scoped-consumer-qualification/artifacts'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
mode=sys.argv[1];assert mode in ('candidate','working','active')
seal=read(A/'stage.json');base=read(R/seal['base_pointer']['manifest_path']);generation=R/base['data_path'];release_id='multiturn-structured-scope-20261021-r1'
C=R if mode=='working' else R/seal['code_root'];rt=A/('runtime-'+mode)
os.environ.update(GENOS_RUNTIME_DIR=str(rt),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(R))
for k in ('TEAM_ID','AD_WORKSPACE','DP'):os.environ.pop(k,None)
if mode=='active':
 sys.path[:0]=[str(R),str(R/'02_BACKEND')]
 import service
 actual=importlib.import_module('service.service');app=actual.application();C=Path(app.state.pipeline.contracts.root)
 binding=getattr(actual,'_BINDING',getattr(getattr(actual,'_runtime',None),'_BINDING',None))
 assert binding['mode']=='local-release' and C==R/'08_DEPLOYMENT/RELEASES'/release_id/'code'
else:
 sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 transport=LocalGemmaTransport(C,R);profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
 app=create_app(R,generation,contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',runtime_root=rt,legal_agent_profile=profile,legal_agent_transport=transport,release={'mode':'local-release','release_id':'integration-check'})
 spec=importlib.util.spec_from_file_location('scoped_candidate_service',C/'service.py');actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
 actual._APP=app;actual._BINDING={'mode':'local-release','code_root':str(C)};binding=actual._BINDING
pipeline=app.state.pipeline;checks={};files=read(A/'release-rebase.json')['staged_files']
checks['exact_serving_files']=all(sha(C/n)==h for n,h in files.items())
checks['data_unchanged']=pipeline.store.path.resolve()==generation.resolve() and sha(generation/'manifest.json')==base['data_manifest_sha256']
checks['model_profile_unchanged']=sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')==base['files']['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json']
checks['ad_disabled']=pipeline.contracts.pipeline['ad_management']['enabled'] is False
checks['knowledge_management_disabled']=pipeline.contracts.pipeline['legal_knowledge']['management_enabled'] is False
health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}));checks['service_health']=health['status']==200
package=type(pipeline).__module__.rsplit('.',1)[0]
qs=importlib.import_module(package+'.legal_agent.query_scope');ur=importlib.import_module(package+'.legal_agent.unit_reading')
checks['helper_loaded_from_selected_root']=Path(qs.__file__).resolve().is_relative_to(C) and sha(Path(qs.__file__))==files['02_BACKEND/semantic_runtime/legal_agent/query_scope.py']
select_documents=importlib.import_module(package+'.team_scope').select_documents
public=set(select_documents(pipeline.store,'financial_team'))&set(pipeline.term_agent.transport.public_scope)
did='3521c3aaa5a735fd';assert did in public
req={'question':'코스닥시장 상장규정 제26조','document_ids':[did],'use_llm':False}
with pipeline.term_agent.open_session(req,query=pipeline.plan(req['question'],[did]),runtime=rt/'source-check') as s:
 matcher=s.sources.matcher
 title=matcher.document_context.get(did,{}).get('document_title') or matcher.documents[did]
 node=next((u for (d,u),n in qs.units(matcher,did) if (did,u) in matcher.stored_coordinates and n.get('family')=='kr_article' and n.get('coordinate_binding',{}).get('mode')!='unresolved'),None)
 assert node is not None
 coordinate=matcher.stored_coordinates[did,node].canonical_surface();quote=title+' '+coordinate
 scope=qs.resolve({'operation':'REPLACE','targets':[{'document':title,'structure':coordinate}],'user_quote':quote},None,matcher,s.sources.scope,quote)
 qs.attach(s.sources,scope);checks['real_title_coordinate_resolved']=scope['targets'][0]['unit_id']==node and qs.documents(s.sources)==[did]
 sid=matcher._unit_sources(did,node)[0]
 hit={'source_id':sid,'document_id':did,'unit_id':node}
 offers=ur.offers(s.sources,hit);assert offers
 record=ur.read(s.sources,hit,offers[0],action_state=ur.read_state(s.sources))
 checks['actual_scoped_original_read']=bool(record['evidence']) and bool(record['offer']['block_ids'])
 checks['read_within_direct_scope']=set(record['offer']['block_ids'])<=qs.permitted_blocks(s.sources,sid)
 checks['zero_model_calls']=s.work.budget()['model_reserved']==0
 definition=app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow',None,'risk_team')
 if mode=='active':
  p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');checks['active_pointer']=p['release_id']==release_id and p['generation']==seal['base_pointer']['generation']+1
  checks['selection_matches_preflight']=pipeline.store.selection.fingerprint==read(A/'consumer-candidate.json')['search_selection_fingerprint']
 out={'status':'PASS' if all(checks.values()) else 'FAIL','mode':mode,'app_injected':mode!='active','checks':checks,'binding':binding,'code_root':str(C.relative_to(R)),
 'source_check':{'document_id':did,'coordinate':coordinate,'scope_hash':scope['hash'],'source_id':sid},'health':health,'workflow_version':definition.manifest['version'],
 'search_selection_fingerprint':pipeline.store.selection.fingerprint,'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'model_calls':0,'genos_executed':False,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
assert all(checks.values()),checks
with (A/f'consumer-{mode}.json').open('x') as f:f.write(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
pipeline.store.close();print(json.dumps({'status':out['status'],'checks':checks,'peak_rss_kib':out['peak_rss_kib']}))
