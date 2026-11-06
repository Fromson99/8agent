"""Verify fresh-process actual service selection, original generation and UI consumer."""
from common import *
OUT=ART/"main"
GOLD=ROOT/"08_DEPLOYMENT/LOCAL/gold_connection_engine_r12"
RELEASE="annex-dash-coordinate-20261105-r1"

from resource_guard import Guard
resource_dir=ART/'main-entry-resource';resource_dir.mkdir(exist_ok=False)
guard=Guard(resource_dir);guard.start()
import asyncio,importlib,os
b={**{'release':read(DES/'baseline.json')['release']},**{'gold_binding':read(OUT/'gold-before.json')['binding'],'gold_files':read(OUT/'gold-before.json')['files']}};stage=read(OUT/'stage.json')
os.environ.update(GENOS_RUNTIME_DIR=str(ART/'selected-entry-runtime'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',
 GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPEN_ROUTER='synthetic-no-model-check')
for key in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE'):
 os.environ.pop(key,None)
sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');assert actual is service
app=actual.application()
try:
 health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}))
 active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
 C=Path(app.state.pipeline.contracts.root)
 checks={'actual_root_entry':Path(actual.__file__).resolve()==ROOT/'service.py',
  'main149':active['generation']==149,'release':active['release_id']==RELEASE,
  'user_directed_authority':active['deployment_basis']=='USER_DIRECTED_CUTOVER' and active['quality_certified'] is False,
  'health200':health['status']==200,'default_local_provider':actual._BINDING['mode']=='local-release',
  'selected_code':C==ROOT/release['code_root'],'selected_inventory':release['files']==stage['files'] ,
  'selected_inventory_hashes_exact':all(sha(C/n)==h for n,h in stage['files'].items()),
  'original_generation':app.state.pipeline.store.path.resolve()==(ROOT/b['release']['data_path']).resolve(),
  'same_source_manifest':sha(app.state.pipeline.store.path/'manifest.json')==b['release']['data_manifest_sha256'],
  'layout4_reader_kept':sha(C/'02_BACKEND/semantic_runtime/oracle_progress_body.py')==b['release']['files']['02_BACKEND/semantic_runtime/oracle_progress_body.py'],
  'workspace_modules_present':all((C/'02_BACKEND/semantic_runtime/ontology_work'/n).is_file() for n in ('wiki_workspace.py','wiki_projection.py','wiki_repository.py','wiki_ui.py')),
  'rollback_main148':read(ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'rollback/ACTIVE_RELEASE.json')['generation']==148}
 from bs4 import BeautifulSoup
 package=type(app.state.pipeline).__module__.rsplit('.',1)[0];w=importlib.import_module(package+'.chat_adapter').views()
 body={'answer':{'text':'확인한 답변','claims':[{'source_ids':['s1']}]},'assembly':{'context':[
  {'id':'s1','document_id':'allowed','document_name':'모의규정','text':'① 확보 원문\n\n② 다음 문단'}]}}
 dom=BeautifulSoup(w._for_markdown(w.render(body)),'html.parser')
 checks['inline_original_exact']=dom.select_one('[data-source-text]').get_text()==body['assembly']['context'][0]['text']
 checks['source_accordion']=bool(dom.select_one('details[data-genos-sources]'))
 # Submit a real no-offer command through the selected service and workflow adapter.
 # A transport tripwire makes any accidental external call a failing observation.
 agent=app.state.pipeline.term_agent
 checks['common_review_enforced']=agent.profile['candidate_navigation']['supervisor_mode']=='enforce'
 checks['common_review_module_exact']=Path(importlib.import_module(package+'.legal_agent.reason_decision_review').__file__).resolve()==C/'02_BACKEND/semantic_runtime/legal_agent/reason_decision_review.py'
 transition=importlib.import_module(package+'.legal_agent.memory_methods')
 checks['current_request_review_fields']=set(transition.TRANSITION_CHECK['required'])=={'valid','reason','request_relation','requested_task'}
 checks['applied_state_guard_present']=callable(transition.assert_transition_applied)
 # Exercise the exact selected source-target consumer and its shared parser.
 target_module=importlib.import_module(package+'.legal_agent.source_goal_control')
 parser_module=importlib.import_module(target_module.find_coordinates.__module__)
 checks['selected_annex_parser_origin']=Path(parser_module.__file__).resolve()==C/'02_BACKEND/lawrag/core/legal_coordinate.py'
 checks['annex_dash_source_target']=target_module.target_coordinate({'coordinate':'별표 17-1','coordinate_scope':'annex'})=='별표 17-1'
 checks['annex_distinct_keys']=len({parser_module.parse_label(t).key() for t in ['별표 17','별표 17-1','별표 17-2']})==3
 checks['article_dash_unchanged']=parser_module.find_coordinates('제6-15조')[0].coordinate.canonical_surface()=='제6-15조'
 sends=[]
 def deny_send(**kwargs):
  sends.append('unplanned-model-send')
  raise AssertionError('The exact review command must not dispatch a model for an empty chat')
 agent.transport.send_once=deny_send
 clause_id='7bbe815ff43b6635'
 team_scope=importlib.import_module(package+'.team_scope')
 teams=team_scope.document_teams(app.state.pipeline.store)[clause_id]
 team='risk_team' if 'risk_team' in teams else sorted(teams)[0]
 inputs={'applied_fields':{'mode':'외규'},'team_id':team,'session_id':'adr1404-selected-entry',
         'request_id':'adr1404-review-no-offer','document_ids':[clause_id],
         'memory':True,'public_question':True,'use_llm':True}
 question='방금 실패한 답변 검토를 이미 확보한 원문을 재사용해서 다시 해줘. 주장과 근거의 연결을 확인하고, 질문에 대한 설명과 남은 미확인을 함께 알려줘.'
 request=w._request_body(question,inputs)
 request['public_question']=True
 assert request['question']=='외규: '+question
 response=asyncio.run(actual.service({},request))
 put(OUT/'selected-chat-probe.json',{'status':response['status'],'request':request,'body':response.get('body'),'physical_sends':len(sends)})
 answer=response.get('body') or {}
 checks.update(selected_review_http=response['status']==200,
               selected_review_state=answer.get('status')=='CLARIFY',
               selected_review_text=(answer.get('answer') or {}).get('text')=='이 대화의 직전 답변에 다시 실행할 검토가 없습니다.',
               selected_review_no_model=not sends,
               selected_core_function=Path(importlib.import_module(package+'.legal_agent.review_actions').__file__).resolve()==C/'02_BACKEND/semantic_runtime/legal_agent/review_actions.py')
 result={'passed':all(checks.values()),'checks':checks,'binding':actual._BINDING,'external_model_calls':len(sends),'oracle_calls':0}
 put(OUT/'main-entry.json',result);assert result['passed'],checks
 print('Actual MAIN149 service',len(checks),'checks PASS; selected annex parser and source target verified')
finally:
 app.state.pipeline.store.close();guard.done.set();guard.thread.join(timeout=3);put(resource_dir/'resource-final.json',guard.check())
