"""Actual selected data and service ingress in isolated technical-test state."""
from pathlib import Path
from types import SimpleNamespace
import asyncio,hashlib,importlib,importlib.util,json,os,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0865-bounded-host-assembly';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mode=sys.argv[1];assert mode in ('candidate','working','active')
f=read(D/'freeze.json');base=read(D/'baseline.json')['release'];generation=R/base['data_path'];C=R if mode=='working' else R/f['code_root']
rt=A/('artifacts/'+mode+'-runtime');os.environ.update(GENOS_RUNTIME_DIR=str(rt),TEAM_ID='risk_team',WORKFLOW_USER_ID='jin',AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',LAWRAG_WORKSPACE_ROOT=str(R));os.environ.pop('DP',None)
sys.dont_write_bytecode=True
if mode=='active':
 sys.path[:0]=[str(R),str(R/'02_BACKEND')];import service
 actual=importlib.import_module('service.service');app=actual.application();C=Path(app.state.pipeline.contracts.root)
 assert actual._BINDING['mode']=='local-release'
else:
 sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 from semantic_runtime.basis_links.api import local_factory
 from semantic_runtime.team_scope import select_documents
 transport=LocalGemmaTransport(C,R);profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
 app=create_app(R,generation,contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',runtime_root=rt,
   legal_agent_profile=profile,legal_agent_transport=transport,memory_identity=lambda _:dict(user_id='jin',team_id='risk_team',document_ids=select_documents(app.state.pipeline.store,'risk_team'),basis_review=True),
   release={'mode':'local-release','release_id':'candidate-test'} )
 spec=importlib.util.spec_from_file_location('basis_entry',C/'service.py');actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual);actual._APP=app;actual._BINDING={'mode':'local-release'}
actual._ad_control=lambda:SimpleNamespace(intercept=lambda *a:None,start_worker=lambda *a:None)
from fastapi.testclient import TestClient
from semantic_runtime.basis_links.resolver import snapshot,targets
from semantic_runtime.team_scope import select_documents
checks={};p=app.state.pipeline;client=TestClient(app)
assert p.store.path.resolve()==generation.resolve() and sha(generation/'manifest.json')==base['data_manifest_sha256']
who={'user_id':'jin','team_id':'risk_team','document_ids':select_documents(p.store,'risk_team'),'basis_review':True}
with p.basis_factory() as authority:
 catalogue=authority.sources.catalogue
 did='11478916f48b00e5';assert did in who['document_ids'] and catalogue[did]['category']=='internal'
 external=next(d for d in who['document_ids'] if catalogue[d]['category']=='external')
 def selection(d):
  row=p.store.db.execute("SELECT block_id,unit_id,text FROM source_block WHERE document_id=? AND length(text)>0 ORDER BY CAST(block_id AS INTEGER) LIMIT 1",(d,)).fetchone()
  return {'document_id':d,'unit_id':row['unit_id'],'scope':'unit' if row['unit_id'] is not None else 'document','spans':[{'block_id':row['block_id'],'start_cp':0,'end_cp':min(len(row['text']),256)}]}
 body={'request_id':'tech-propose','internal':[selection(did)],'external':[selection(external)],'kind':'BASIS','reason':'격리된 기술 검사 후보. 법적 근거 관계를 주장하지 않습니다.'}
response=asyncio.run(actual.service({}, {'API_TYPE':'BASIS_LINKS_PROPOSE','json':body}));assert response['status']==200,response
checks['actual_service_exact_candidate']=True
listed=asyncio.run(actual.service({}, {'API_TYPE':'BASIS_LINKS_LIST','internal_document_id':did}));assert listed['status']==200
view=listed['body'];approved=asyncio.run(actual.service({}, {'API_TYPE':'BASIS_LINKS_REVIEW','json':{'request_id':'tech-approve','view_id':view['view_id'],'rows':[1],'action':'approve'}}));assert approved['status']==200 and approved['body']['status']=='completed'
checks['actual_service_human_review']=True
with p.basis_factory() as authority:
 current=snapshot(authority,who,[did]);queue=targets(authority,who,current);assert len(queue)==1
 checks['next_request_live_priority']=True
 expected=queue[0]['endpoint']
 request={'question':catalogue[did]['name']+' 근거 확인','document_ids':[did,external],'use_llm':False}
 with p.term_agent.open_session(request,query=p.plan(request['question'],[did,external]),runtime=rt/'native-check') as session:
  node=session.sources.source.handle('U',{'document_id':external,'unit_id':expected['unit_id'],'source_id':None,'read_segments':[{k:x[k] for k in ('block_id','start_cp','end_cp')} for x in expected['spans']]})
  receipt=session.sources.source.execute({'tool':'read_node','args':{'node':node,'cursor':None},'reason':'격리된 승인 원문 기술 검사'})
  assert receipt['status']=='OK' and receipt['items'];assert session.work.budget()['model_reserved']==0
  checks['actual_source_tool_exact_read']=True
runtime=app.state.workflow_runtime
for wid in ('risk_team_compare_workflow','internal_basis_discovery_workflow'):
 definition=runtime.registry.resolve(wid,None,'risk_team')
 request={'workflow_id':wid,'workflow_version':definition.manifest['version'],'principal':who,'document_ids':who['document_ids'],'use_llm':True}
 binding=runtime.services.binding(request,definition.manifest)
 assert binding['external_authorization']['scope_document_ids']==who['document_ids']
 checks[wid+'_actual_model_authorization']=True
checks['review_page']=client.get('/basis/').status_code==200
checks['registered_discovery']=any(w['id']=='internal_basis_discovery_workflow' for w in p.contracts.pipeline['workflows']['registered'])
health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}));checks['actual_service_health']=health['status']==200
with p.basis_factory() as authority:
 row=authority.list(who,did)['items'][0];value=authority.review(who,{'request_id':'tech-revoke','action':'revoke','items':[{'link_id':row['link']['link_id'],'revision':row['link']['revision'],'view_hash':row['view_hash']}]})
 assert value['status']=='completed' and not targets(authority,who,current)
 checks['revocation_invalidates_used_snapshot']=True
value={'status':'PASS','mode':mode,'checks':checks,'code_root':str(C.relative_to(R)),'service_entry':str(Path(actual.__file__).resolve().relative_to(R)),
 'service_sha256':sha(Path(actual.__file__)),'app_injected':mode!='active','data_manifest_sha256':sha(generation/'manifest.json'),
 'search_selection_fingerprint':p.store.selection.fingerprint,'runtime':str(rt.relative_to(R)),'model_calls':0,'genos_deployed':False,'health':health}
(A/('artifacts/'+mode+'-consumer.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':value['status'],'checks':checks},ensure_ascii=False));p.store.close()
