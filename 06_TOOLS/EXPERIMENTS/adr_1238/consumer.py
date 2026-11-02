from common import *
import os,asyncio,importlib,resource,sqlite3
resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
mode=sys.argv[1];ontology=sys.argv[2] if len(sys.argv)>2 else 'off'
assert mode in ('candidate','active') and ontology in ('off','on','db')
b=read(DES/'baseline.json');f=read(DES/'freeze.json');C=ROOT/f['code_root'];rt=ART/('runtime-'+mode+'-'+ontology)
os.environ.update(GENOS_RUNTIME_DIR=str(rt),AD_WORKER_ENABLED='0',GENOS_AUTO_WARMUP='0',GENOS_RESIDENT_DATA='off',MALLOC_ARENA_MAX='1',LAWRAG_WORKSPACE_ROOT=str(ROOT),OPEN_ROUTER='synthetic-local-check')
for k in ('TEAM_ID','AD_WORKSPACE','DP','GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_RAG_ONTOLOGY_CONFIG','GENOS_RAG_ONTOLOGY_ENABLED'):os.environ.pop(k,None)
if ontology in ('on','db'):os.environ['GENOS_RAG_ONTOLOGY_ENABLED']='on'
if ontology=='db':
 db=ART/'empty-ontology.sqlite';sqlite3.connect(db).close();p=ART/'empty-ontology-config.json'
 put(p,{'version':'ontology-connection-v1','environment':'local','database':{'kind':'sqlite-local','path':str(db)}});os.environ['GENOS_RAG_ONTOLOGY_CONFIG']=str(p)
if mode=='active':
 sys.path[:0]=[str(ROOT),str(ROOT/'02_BACKEND')]
 import service
 actual=importlib.import_module('service.service');app=actual.application();C=Path(app.state.pipeline.contracts.root)
 binding=getattr(actual,'_BINDING',getattr(getattr(actual,'_runtime',None),'_BINDING',None))
 health=asyncio.run(actual.service({}, {'API_TYPE':'HEALTH'}))
else:
 assert ontology=='off'
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
dom=BeautifulSoup(w._for_markdown(w.render(body)),'html.parser')
profile=p.term_agent.profile;transport=p.term_agent.transport
checks={'health200':health['status']==200,'all489_bytes':len(f['files'])==489 and all(sha(C/n)==h for n,h in f['files'].items()),'renderer_selected':Path(w.__file__).resolve()==C/'08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','chat_selected':Path(chat.__file__).is_relative_to(C),'source_accordion':bool(dom.select_one('details[data-genos-sources] > div > details[data-genos-source]')),'original_exact':dom.select_one('[data-source-text]').get_text()==body['assembly']['context'][0]['text'],'default_closed':not dom.select('details[open]'),'data_unchanged':p.store.path.resolve()==(ROOT/b['manifest']['data_path']).resolve(),'data_manifest_unchanged':sha(p.store.path/'manifest.json')==b['manifest']['data_manifest_sha256'],'model_unchanged':sha(C/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')==b['manifest']['files']['00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'],'budget_unchanged':all(profile[k]==read(ROOT/b['manifest']['code_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')[k] for k in ('max_output_tokens','max_model_attempts','max_tool_actions','wall_seconds'))}
for group,names in [('legal_agent',['need_continuity','decision_projection','judgment_changes','investigation_supervisor','requirement_coverage','journal_storage','storage_admission','narrative_answer','wire_schema','read_judgment_final','ontology_assessment','navigation_input','law_navigation','transport','local_gemma']),('ontology_work',['profile','observations','accumulation','domain_workflow','profile_schema','glossary_binding','assembly_compiler','authoring_model','configuration','recorded_fields','authoring_semantics'])]:
 for n in names:checks['selected_'+n]=Path(importlib.import_module(package+'.'+group+'.'+n).__file__).is_relative_to(C)
js=importlib.import_module(package+'.legal_agent.journal_storage');db=js.connect(':memory:');js.initialize(db)
raw='① 동일 원문과 판단 이력\n'*300
stored=js.store(db,raw);checks['storage_roundtrip']=js.restore(db,stored)==raw
checks['legacy_plain_read']=js.restore(db,'과거 원문')=='과거 원문';db.close()
ws=importlib.import_module(package+'.legal_agent.wire_schema');ps=importlib.import_module(package+'.ontology_work.profile_schema')
domain=read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json')
for stage,maker in [('NORMALIZE',ps.observation_schema),('ACCUMULATE',ps.accumulation_schema)]:
 schema=maker(domain);wire,receipt=ws.project_request({'response_format':{'type':'json_schema','json_schema':{'strict':True,'name':'check','schema':schema}}})
 checks['schema_size_'+stage]=receipt['wire_schema_chars']==read(ART/'schema-sizes.json')[stage]['wire_chars'] and receipt['changed']
 checks['schema_strict_'+stage]=wire['response_format']['json_schema']['strict'] is True
ob=importlib.import_module(package+'.ontology_work.observations')
r=ob.envelope({'first':'가상문장','second':'가상메타'},namespace='synthetic',run_id='service',event_id='check',sequence=0,source_snapshot='synthetic',producer_binding='synthetic',acl_ref='synthetic',document_ids=[])
dynamic=ob.normalization_schema(r,{'output_schema':ps.observation_schema(domain)})
cov=dynamic['properties']['coverage']
checks['request_bound_coverage_keys']=cov['type']=='object' and set(cov['required'])=={'/first','/second'} and cov['additionalProperties'] is False
checks['coverage_state_refs']=all(v['anyOf'][0]['properties']['observation_ids']['minItems']==1 and v['anyOf'][1]['properties']['observation_ids']['maxItems']==0 for v in cov['properties'].values())
roles=importlib.import_module(package+'.ontology_work.recorded_fields')
role_schema=roles.request_schema(dynamic,r)
fields=role_schema['properties']['observations']['items']['properties']
checks['recorded_roles_nullable']=all(fields[k]['anyOf'][0]=={'type':'null'} for k in ('recorded_reason','recorded_purpose'))
checks['old_role_output_absent']=not {'reason','purpose'} & fields.keys()
semantics=importlib.import_module(package+'.ontology_work.authoring_semantics')
checks['source_only_stage_selected']='SOURCE_ANALYSIS' in (C/'02_BACKEND/semantic_runtime/ontology_work/domain_workflow.py').read_text()
checks['no_role_word_whitelist']=not hasattr(roles,'LABELS')
checks['canonical_profile_schema_unchanged']=sha(C/'02_BACKEND/semantic_runtime/ontology_work/profile_schema.py')==b['manifest']['files']['02_BACKEND/semantic_runtime/ontology_work/profile_schema.py']
checks['same_rollback_journal_reader']=sha(C/'02_BACKEND/semantic_runtime/legal_agent/journal_storage.py')==b['manifest']['files']['02_BACKEND/semantic_runtime/legal_agent/journal_storage.py']
model_contract=importlib.import_module(package+'.legal_agent.model_contract')
request=model_contract.structured_request(model=transport.binding['model'],max_tokens=profile['max_output_tokens'],messages=[{'role':'user','content':'synthetic binding check'}],schema_name='check',schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False})
from lawrag.core import request_deadline as dt
import httpx
from unittest.mock import patch
sent=[]
def respond(req):
 sent.append(json.loads(req.content));return httpx.Response(200,json={'model':transport.binding['model'],'provider':'Parasail','choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}],'usage':{'prompt_tokens':10,'completion_tokens':20}})
route=importlib.import_module(package+'.legal_agent.provider_routing').route;request['provider']=route(transport.provider_policy['providers'][0]);original=dt.post_json
def mock_post(url,**kw):return original(url,**kw,transport=httpx.MockTransport(respond))
with patch.object(dt,'post_json',mock_post):transport.send_once(body=request,ticket={'remaining_seconds':30,'provider_index':0})
checks['mock_http_exactly_one']=len(sent)==1
checks['no_output_cap']=not {'max_tokens','max_completion_tokens','max_output_tokens'}&set(sent[0])
checks['primary_parasail']=sent[0]['provider']['only']==['parasail/fp8']
checks['429_switch_unchanged']=transport.provider_policy['providers'][1]['tag']=='near-ai/fp8' and transport.provider_policy['max_provider_switches']==1 and transport.provider_policy['switch_http_status']==[429]
checks['transport_deadline_selected']=Path(dt.__file__).is_relative_to(C)
checks['ontology_enabled']=profile['candidate_navigation']['ontology_enabled'] is (ontology!='off')
checks['ontology_context']=profile['candidate_navigation']['ontology_context']==({'mode':'DB'} if ontology=='db' else {'mode':'A0'})
checks['all_working_files_exact']=all(sha(ROOT/n)==h for n,h in f['files'].items()) if mode=='active' else True
if mode=='active':
 active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
 checks.update(main124=active['generation']==124,release_selected=active['release_id']==RELEASE,qualified=active['deployment_basis']=='VALIDATED_ADR_PROMOTION',local_binding=binding['mode']=='local-release',release_code_matches=C==ROOT/release['code_root'],release_inventory_exact=release['files']==f['files'])
 checks['ontology_binding']=binding['ontology']=={'enabled':ontology!='off','data_configured':ontology=='db','active':ontology=='db','fallback':None if ontology=='db' else 'ordinary-rag'}
result={'passed':all(checks.values()),'checks':checks,'mode':mode,'ontology':ontology,'binding':binding,'health':health,'code_root':str(C.relative_to(ROOT)),'external_model_calls':0,'mock_http_calls':len(sent),'genos_deployed':False,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
put(ART/f'consumer-{mode}-{ontology}.json',result);p.store.close()
assert result['passed'],[k for k,v in checks.items() if not v]
print(mode,ontology,len(checks),'checks PASS')
