"""Actual service entrypoint HEALTH and selected-code binding with a small memory cap."""
from common import *
import sys,os,resource,asyncio,importlib,importlib.util
sys.dont_write_bytecode=True
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
mode=sys.argv[1];assert mode in ('candidate','working','active')
s=read(ART/'stage.json');base=read(ROOT/s['base_pointer']['manifest_path']);C=ROOT if mode=='working' else ROOT/s['roots']['candidate']
rt=ART/('runtime-service-'+mode)
os.environ.update(GENOS_RUNTIME_DIR=str(rt),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
for k in ('TEAM_ID','AD_WORKSPACE','DP'):os.environ.pop(k,None)
if mode=='active':
 sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
 import service
 module=importlib.import_module('service.service');app=module.application();C=Path(app.state.pipeline.contracts.root)
 binding=getattr(module,'_BINDING',getattr(getattr(module,'_runtime',None),'_BINDING',None))
 assert binding['mode']=='local-release'
else:
 sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 transport=LocalGemmaTransport(C,ROOT);profile=read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json');profile['model_binding']=transport.binding
 app=create_app(ROOT,ROOT/base['data_path'],contracts_root=C,workspace_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',runtime_root=rt,legal_agent_profile=profile,legal_agent_transport=transport,release={'mode':'local-release','release_id':'qualification'})
 spec=importlib.util.spec_from_file_location('qualified_service_entry',C/'service.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module._APP=app;module._BINDING={'mode':'local-release','code_root':str(C)};binding=module._BINDING
p=app.state.pipeline;health=asyncio.run(module.service({}, {'API_TYPE':'HEALTH'}))
package=type(p).__module__.rsplit('.',1)[0];ss=importlib.import_module(package+'.legal_agent.structure_selection');entry=importlib.import_module(package+'.legal_agent.request_entry')
checks={'service_health':health['status']==200,'all419_code_files_exact':all(sha(C/n)==h for n,h in s['files']['candidate'].items()),'native_selected_helpers':Path(ss.__file__).resolve().is_relative_to(C),
 'data_unchanged':p.store.path.resolve()==(ROOT/base['data_path']).resolve() and sha(p.store.path/'manifest.json')==base['data_manifest_sha256'],
 'profile_unchanged':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')==base['files']['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'],
 'required_scope_wired':'search_scope_change' in entry.schema(True,model=True)['properties']['command']['anyOf'][0]['required'],
 'bound_operator_wired':any(x['properties']['kind']['const']=='BOUND' for x in ss.CLAUSE['anyOf'])}
workflow=app.state.workflow_runtime.registry.resolve('risk_team_compare_workflow',None,'risk_team')
if mode=='active':
 pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');checks['pointer_selected']=C==ROOT/'08_DEPLOYMENT/RELEASES'/pointer['release_id']/'code' and pointer['generation']==s['base_pointer']['generation']+1
out={'status':'PASS' if all(checks.values()) else 'FAIL','mode':mode,'checks':checks,'app_injected':mode!='active','binding':binding,'code_root':str(C.relative_to(ROOT)),'health':health,'workflow_version':workflow.manifest['version'],'profile_sha256':sha(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'),'model_calls':0,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
 'limits':'HEALTH and actual code/profile/data binding only. Full original READ is exercised by exact-code synthetic API contracts and live model boundary tests. Whole local corpus not loaded alongside the existing unrelated embedding job. GENOS not contacted.'}
save(ART/f'consumer-{mode}.json',out);p.store.close();assert all(checks.values()),checks
print(json.dumps({'status':out['status'],'mode':mode,'checks':checks,'peak_rss_kib':out['peak_rss_kib']}))
