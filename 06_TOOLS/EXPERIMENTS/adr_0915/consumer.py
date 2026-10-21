"""Actual local ingress binding and bounded source read; no external model."""
from pathlib import Path
import asyncio,hashlib,importlib,importlib.util,json,os,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0915-answer-first-followup-provenance';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mode=sys.argv[1];assert mode in ('candidate','working','active')
b=read(D/'retained-binding.json');base=read(D/'baseline.json')['manifest'];generation=R/base['data_path'];C=R if mode=='working' else R/b['code_root'];rt=A/('artifacts/'+mode+'-runtime')
os.environ.update(GENOS_RUNTIME_DIR=str(rt),TEAM_ID='financial_team',AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(R));os.environ.pop('DP',None);sys.dont_write_bytecode=True
if mode=='active':
 sys.path[:0]=[str(R),str(R/'02_BACKEND')];import service
 actual=importlib.import_module('service.service');app=actual.application();C=Path(app.state.pipeline.contracts.root)
 assert actual._BINDING['mode']=='local-release'
else:
 sys.path[:0]=[str(C/'02_BACKEND'),str(C),str(R/'02_BACKEND')]
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 transport=LocalGemmaTransport(C,R);profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
 app=create_app(R,generation,contracts_root=C,workspace_root=R,provider=object(),implementation='legal-agent-unified-v6',runtime_root=rt,legal_agent_profile=profile,legal_agent_transport=transport,release={'mode':'local-release','release_id':'technical-candidate'})
 spec=importlib.util.spec_from_file_location('answer_first_entry',C/'service.py');actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual);actual._APP=app;actual._BINDING={'mode':'local-release','candidate_code_root':str(C)}
p=app.state.pipeline
checks={}
checks['serving_files_exact']=all(sha(C/n)==h for n,h in b['serving_files'].items())
checks['selected_data_exact']=p.store.path.resolve()==generation.resolve() and sha(generation/'manifest.json')==base['data_manifest_sha256']
from semantic_runtime.legal_agent.law_candidates import answer_first
checks['answer_first_enabled']=answer_first(p.term_agent.profile)
checks['pipeline_loaded_from_target']=Path(sys.modules[type(p).__module__].__file__).resolve().is_relative_to(C)
health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}));checks['actual_health']=health['status']==200
from semantic_runtime.team_scope import select_documents
scope=set(select_documents(p.store,'financial_team'))&set(p.term_agent.transport.public_scope);did='3521c3aaa5a735fd';checks['financial_public_scope']=did in scope
req={'question':'코스닥시장 상장규정 제26조','document_ids':[did],'use_llm':False}
with p.term_agent.open_session(req,query=p.plan(req['question'],[did]),runtime=rt/'source-check') as s:
 source=s.sources.source
 row=p.store.db.execute('SELECT unit_id FROM source_block WHERE document_id=? AND unit_id IS NOT NULL AND length(text)>0 ORDER BY CAST(block_id AS INTEGER) LIMIT 1',(did,)).fetchone()
 node=source.handle('U',{'document_id':did,'unit_id':row['unit_id'],'source_id':None})
 receipt=source.execute({'tool':'read_node','args':{'node':node,'cursor':None},'reason':'격리된 로컬 소비자 원문 검증'})
 checks['actual_source_read']=receipt['status'] in ('OK','TRUNCATED') and bool(receipt['items'])
 checks['zero_model_calls']=s.work.budget()['model_reserved']==0
assert all(checks.values()),checks
out={'status':'PASS','checks':checks,'mode':mode,'app_injected':mode!='active','code_root':str(C.relative_to(R)),'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'search_selection_fingerprint':p.store.selection.fingerprint,'service_entry':str(Path(actual.__file__).resolve().relative_to(R)),'health':health,'model_calls':0,'genos_executed':False}
(A/f'artifacts/{mode}-consumer.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':'PASS','checks':checks}));p.store.close()
