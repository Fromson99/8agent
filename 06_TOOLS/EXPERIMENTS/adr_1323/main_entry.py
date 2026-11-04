"""Verify fresh-process actual service selection, original generation and UI consumer."""
from common import *
OUT=ART/"main"
GOLD=ROOT/"08_DEPLOYMENT/LOCAL/gold_connection_engine_r12"
RELEASE="genos-oracle-startup-20261104-r1"
sys.path.insert(0,str(ROOT/'06_TOOLS/EXPERIMENTS/adr_1317'))
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
  'main140':active['generation']==140,'release':active['release_id']==RELEASE,
  'user_directed_authority':active['deployment_basis']=='USER_DIRECTED_CUTOVER' and active['quality_certified'] is False,
  'health200':health['status']==200,'default_local_provider':actual._BINDING['mode']=='local-release',
  'selected_code':C==ROOT/release['code_root'],'selected_inventory':release['files']==stage['files'] ,
  'selected_inventory_hashes_exact':all(sha(C/n)==h for n,h in stage['files'].items()),
  'original_generation':app.state.pipeline.store.path.resolve()==(ROOT/b['release']['data_path']).resolve(),
  'same_source_manifest':sha(app.state.pipeline.store.path/'manifest.json')==b['release']['data_manifest_sha256'],
  'layout4_reader_kept':sha(C/'02_BACKEND/semantic_runtime/oracle_progress_body.py')==b['release']['files']['02_BACKEND/semantic_runtime/oracle_progress_body.py'],
  'workspace_modules_present':all((C/'02_BACKEND/semantic_runtime/ontology_work'/n).is_file() for n in ('wiki_workspace.py','wiki_projection.py','wiki_repository.py','wiki_ui.py')),
  'rollback_main139':read(ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'rollback/ACTIVE_RELEASE.json')['generation']==139}
 from bs4 import BeautifulSoup
 package=type(app.state.pipeline).__module__.rsplit('.',1)[0];w=importlib.import_module(package+'.chat_adapter').views()
 body={'answer':{'text':'확인한 답변','claims':[{'source_ids':['s1']}]},'assembly':{'context':[
  {'id':'s1','document_id':'allowed','document_name':'모의규정','text':'① 확보 원문\n\n② 다음 문단'}]}}
 dom=BeautifulSoup(w._for_markdown(w.render(body)),'html.parser')
 checks['inline_original_exact']=dom.select_one('[data-source-text]').get_text()==body['assembly']['context'][0]['text']
 checks['source_accordion']=bool(dom.select_one('details[data-genos-sources]'))
 result={'passed':all(checks.values()),'checks':checks,'binding':actual._BINDING,'external_model_calls':0,'oracle_calls':0}
 put(OUT/'main-entry.json',result);assert result['passed'],checks
 print('Actual MAIN140 service',len(checks),'checks PASS')
finally:
 app.state.pipeline.store.close();guard.done.set();guard.thread.join(timeout=3);put(resource_dir/'resource-final.json',guard.check())
