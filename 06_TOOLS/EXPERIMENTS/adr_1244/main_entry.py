"""Read the actual selected local service entry with the default data provider."""
from common import *
import asyncio,importlib,os
b=read(DES/'baseline.json');f=read(DES/'freeze.json')
os.environ.update(GENOS_RUNTIME_DIR=str(ART/'nfs-main-entry'),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',
 GENOS_RESIDENT_DATA='off',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPEN_ROUTER='synthetic-local-check')
for key in ('DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED','TEAM_ID','AD_WORKSPACE'):
 os.environ.pop(key,None)
sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
import service
actual=importlib.import_module('service.service');assert actual is service
app=actual.application();health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}))
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
binding=actual._BINDING;C=Path(app.state.pipeline.contracts.root)
checks={'actual_root_entry':Path(actual.__file__).resolve()==ROOT/'service.py',
 'main128':active['generation']==128,'release':active['release_id']==RELEASE,
 'qualified':active['deployment_basis']=='VALIDATED_ADR_PROMOTION','health200':health['status']==200,
 'nfs_default_preserved':binding['mode']=='local-release','selected_code':C==ROOT/release['code_root'],
 'selected495':release['files']==f['files'] and all(sha(C/n)==h for n,h in f['files'].items()),
 'working495':all(sha(ROOT/n)==h for n,h in f['files'].items()),
 'original_generation':app.state.pipeline.store.path.resolve()==(ROOT/b['manifest']['data_path']).resolve(),
 'same_source_manifest':sha(app.state.pipeline.store.path/'manifest.json')==b['manifest']['data_manifest_sha256']}
from bs4 import BeautifulSoup
package=type(app.state.pipeline).__module__.rsplit('.',1)[0]
w=importlib.import_module(package+'.chat_adapter').views()
body={'answer':{'text':'확인한 답변','claims':[{'source_ids':['s1']}]},'assembly':{'context':[
 {'id':'s1','document_id':'allowed','document_name':'모의규정','text':'① 확보 원문\n\n② 다음 문단'}]}}
dom=BeautifulSoup(w._for_markdown(w.render(body)),'html.parser')
checks['inline_original_exact']=dom.select_one('[data-source-text]').get_text()==body['assembly']['context'][0]['text']
checks['source_accordion']=bool(dom.select_one('details[data-genos-sources]'))
result={'passed':all(checks.values()),'checks':checks,'binding':binding,'external_model_calls':0,'field_deployed':False}
put(OUT/'main-entry.json',result);assert result['passed'],checks
app.state.pipeline.store.close();print('Actual MAIN128 default entry:',len(checks),'checks PASS')
