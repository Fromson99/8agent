from common import *
import os,asyncio,importlib,resource
resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
mode=sys.argv[1];assert mode in ('candidate','active')
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root'];rt=ART/('runtime-'+mode)
os.environ.update(GENOS_RUNTIME_DIR=str(rt),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPEN_ROUTER='synthetic-local-check')
for k in ('TEAM_ID','AD_WORKSPACE','DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED'):os.environ.pop(k,None)
if mode=='active':
 sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
 import service
 actual=importlib.import_module('service.service');app=actual.application();C=Path(app.state.pipeline.contracts.root)
 binding=getattr(actual,'_BINDING',getattr(getattr(actual,'_runtime',None),'_BINDING',None))
 health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}))
else:
 sys.path[:0]=[str(C),str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 transport=LocalGemmaTransport(C,ROOT);profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
 app=create_app(ROOT,ROOT/b['manifest']['data_path'],contracts_root=C,workspace_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',runtime_root=rt,legal_agent_profile=profile,legal_agent_transport=transport,release={'mode':'local-release','release_id':'integration-check'})
 from fastapi.testclient import TestClient
 health={'status':TestClient(app).get('/health').status_code};binding={'mode':'candidate','code_root':str(C)}
p=app.state.pipeline;package=type(p).__module__.rsplit('.',1)[0];chat=importlib.import_module(package+'.chat_adapter');w=chat.views()
from bs4 import BeautifulSoup
body={'answer':{'text':'확인한 답변입니다.','claims':[{'source_ids':['s1']}]},'assembly':{'context':[{'id':'s1','document_id':'allowed','document_name':'모의규정','text':'① 원문입니다.\n\n② 다음 문단입니다.'}]}}
html=w._for_markdown(w.render(body));dom=BeautifulSoup(html,'html.parser')
checks={'health200':health['status']==200,'all466_bytes':len(f['files'])==466 and all(sha(C/n)==h for n,h in f['files'].items()),'source_module_selected':Path(w.__file__).resolve()==C/PRODUCT,'chat_module_selected':Path(chat.__file__).is_relative_to(C),'display_revision':w.ANSWER_DISPLAY_REVISION=='workflow-source-accordion-20261029-r1','nested_cards':bool(dom.select_one('details[data-genos-sources] > div > details[data-genos-source]')),'original_exact':dom.select_one('[data-source-text]').get_text()==body['assembly']['context'][0]['text'],'default_closed':not dom.select('details[open]'),'data_unchanged':p.store.path.resolve()==(ROOT/b['manifest']['data_path']).resolve(),'data_manifest_unchanged':sha(p.store.path/'manifest.json')==b['manifest']['data_manifest_sha256'],'profile_unchanged':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')==b['manifest']['files']['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json']}
if mode=='active':
 active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
 checks.update(main118=active['generation']==118,release_selected=active['release_id']==RELEASE,qualified=active['deployment_basis']=='VALIDATED_ADR_PROMOTION',local_binding=binding['mode']=='local-release',release_code_matches=C==ROOT/release['code_root'],release_inventory_exact=release['files']==f['files'])
result={'passed':all(checks.values()),'checks':checks,'mode':mode,'binding':binding,'health':health,'code_root':str(C.relative_to(ROOT)),'external_model_calls':0,'genos_deployed':False,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
put(ART/f'consumer-{mode}.json',result);p.store.close()
assert result['passed'],checks
print(mode,len(checks),'checks PASS')
