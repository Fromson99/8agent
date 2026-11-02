from pathlib import Path
import hashlib,json,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1233-gold-ontology-on-live';D=A/'artifacts/design';O=A/'artifacts/run-001'
P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
D.mkdir(parents=True);O.mkdir()
m=read(A/'실험/manifest.json');binding=read(P/'binding.json');C=R/binding['engine_root']
question='상법 제369조에 따른 1주당 의결권 수와 자기주식·주식 상호보유의 의결권 제한은 어떻게 되나요?'
cases=[{'id':'gold-369','request':{'API_TYPE':'RAG_ASK','json':{'question':question,'document_ids':['7bbe815ff43b6635'],'use_llm':True}}}]
put(D/'cases.json',cases)
put(D/'authorization.json',{'kind':'USER_AUTHORIZED_GOLD_ONTOLOGY_CHECK','instruction':'ON해보고 돌아가는지 확이냏봐','session_id':m['reservation']['session_id'],'question':question,'scope':'New public-law question; one current Gold public Commercial Act document, retrieved originals, glossary references and delegated source-bound publications. No reference answer or private source.','endpoint':'https://openrouter.ai/api/v1','providers':['parasail/fp8','near-ai/fp8'],'model':'qwen/qwen3.8-27b','dispatches':'One question once; 40 physical max, 429 only one gateway-owned provider switch, UNKNOWN ends run','prior_public_source_grant':'Selected LocalQwen38Transport grant; validated before dispatch'})
criteria={'hypothesis':'ON/DB and the current mapped repository let the existing native API consume an actual published Gold ontology and issue a source-bound final answer.','success':['HTTP200 with nonempty final saved answer','At least one actual Gold publication in model input and selected ontology path in final answer','Original text/hash/ACL preserved; actual wire recorded; no corpus SQLite fallback','No UNKNOWN/resource/integrity failure; physical attempts equal gateway budget'],'limits':{'physical_model':40,'tools':1024,'sql':10000,'seconds':1800,'min_available_GiB':3,'max_RSS_GiB':5,'max_swap_growth_MiB':128,'min_disk_GiB':80},'sample':'One known source-bound public article369 question; in-sample functional check, not quality or speed A/B','external_retry':False,'user_authorized_configuration':'Only separate Gold connector ON/DB; MAIN123 code/profile and GENOS unchanged','transport':'ExperimentClient one physical request per native reserved ticket; native gateway alone owns confirmed429 switch'}
put(D/'criteria.json',criteria)
put(D/'before.json',{'active_main_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'connector_binding_sha256':sha(P/'binding.json'),'engine_files':len(binding['engine_files']),'publication_receipts':read(R/'09_ARTIFACTS/AUDITS/20261030-gold-ontology-publication/publication-receipts.json'),'graph_errors_before':16})
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Actual Gold ontology delivered + selected + final answer issued (separate gates)',success_criteria=criteria['success'],failure_criteria=['Any required gate false','UNKNOWN/resource/hash/ACL failure ends run'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')})
m['design']['arms'][0].update(changes='Historical OFF real CM009 failure, not rerun or paired',controls='Fixed MAIN120; original failure kept')
m['design']['arms'][1].update(changes='Explicit ON/DB on renamed physical schema with three existing publications; public article369 once',controls='Same source reader, hash/ACL, frozen engine and native budgets; no answer injection')
m['runs'][0].update(arm_ids=['live'],selection_rule=criteria['sample'],artifact_path=str((O/'result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='Public Gold Commercial Act article369 live question',version='20261030-1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
# Technical connection exercise; exact source/ontology lineage is audited separately.
reason='Existing ranking unchanged; one functional native API connection check, no retrieval quality comparison. Actual candidate/source/ontology delivery is recorded separately without golden recall claims.'
m['retrieval_accounting'].update(changed=False,corpus_total=1,not_applicable_reason=reason)
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
target='08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py'
S=ac.snapshot(A,'live',[target],experiment_id=m['experiment_id'],arm_id='live',run_ids=['run-001']);SP=S/'snapshot'
code=(SP/target).read_text()
addition='''def load_profile(settings=None):
 value=read(ROOT/read(HERE/'binding.json')['engine_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')
 path=Path(settings) if settings is not None else HERE/'ontology_settings.json'
 if not path.exists():return value
 cfg=read(path)
 if set(cfg)!={'schema_version','enabled'} or cfg['schema_version']!='gold-ontology-settings-v1' or type(cfg['enabled']) is not bool:
  raise ValueError('Gold ontology settings shape')
 policy=value['candidate_navigation'];policy['ontology_enabled']=cfg['enabled']
 policy['ontology_context']={'mode':'DB' if cfg['enabled'] else 'A0'}
 return value

'''
code=code.replace('def load_runtime():',addition+'def load_runtime():')
code=code.replace('def open_store(*,config=None,','def open_store(*,ontology_settings=None,config=None,')
code=code.replace('   store=runtime.Store(request)','   store=runtime.Store(request)\n   store.gold_profile=load_profile(ontology_settings)')
code=code.replace("sub=p.add_subparsers(dest='action',required=True)","p.add_argument('--ontology-settings')\n sub=p.add_subparsers(dest='action',required=True)")
code=code.replace('with open_store(config=args.config,','with open_store(ontology_settings=args.ontology_settings,config=args.config,')
code=code.replace("if hasattr(store,'gold_ports'):value['physical_mapping']=store.gold_ports.preflight","value['ontology']={k:v for k,v in store.gold_profile['candidate_navigation'].items() if k in ('ontology_enabled','ontology_context','ontology_direct_assessment')}\n   if hasattr(store,'gold_ports'):value['physical_mapping']=store.gold_ports.preflight")
(SP/target).write_text(code)
settings='08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/ontology_settings.json';put(SP/settings,{'schema_version':'gold-ontology-settings-v1','enabled':True});ac.register_file(S,settings,upstream_state='absent')
source=(R/binding['adapter_root']/'engine_live.py').read_text()
top='''from pathlib import Path
import importlib.util,sys,os
from contextlib import nullcontext
R=Path('/home/jin/8-AGENT');P=R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
FROZEN=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('gold_on_connector',FROZEN/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py')
gold=importlib.util.module_from_spec(spec);spec.loader.exec_module(gold);gold.HERE=P;gold.ROOT=R
os.environ.update(OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
GOLD_CONTEXT=gold.open_store(ontology_settings=FROZEN/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/ontology_settings.json',documents=['7bbe815ff43b6635'])
GOLD_OPEN=GOLD_CONTEXT.__enter__()
from engine_runtime import *
PARENT_O=O
A=R/'04_EXPERIMENTS/ADR/ADR-1233-gold-ontology-on-live';D=A/'artifacts/design';O=A/'artifacts/run-001'
base_guard=guard;resource_samples=[];initial_resource=base_guard();initial_swap=initial_resource['SwapTotal']-initial_resource['SwapFree']
def guard():
 value=base_guard();value['host_swap_growth']=value['SwapTotal']-value['SwapFree']-initial_swap
 if value['host_swap_growth']>128*1024**2:raise RuntimeError('HOST_SWAP_GROWTH')
 if len(resource_samples)<4000:resource_samples.append(value)
 return value
'''
source=source.replace('from engine_runtime import *',top)
source=source.replace("case_id=sys.argv[1];assert case_id in ('cm-007','cm-009')","case_id=sys.argv[1];assert case_id=='gold-369' and len(sys.argv)==2")
source=source.replace("read(O/'latest-check.json')","read(PARENT_O/'latest-check.json')").replace("read(O/'vector-check/result.json')","read(PARENT_O/'vector-check/result.json')").replace("read(O/'glossary-id-check/result.json')","read(PARENT_O/'glossary-id-check/result.json')")
source=source.replace('allowed=set(docs())',"allowed=set(case['request']['json']['document_ids'])")
source=source.replace("read(C/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')","GOLD_OPEN[0].gold_profile")
source=source.replace('USER_AUTHORIZED_CM_EXPERIMENT','USER_AUTHORIZED_GOLD_ONTOLOGY_CHECK')
source=source.replace('with connect() as conn:\n   req,transport=open_engine(conn,release_id=read(O/\'build-result.json\')[\'query_id\'],seconds=1800);store=Store(req)', 'with nullcontext(GOLD_OPEN) as (store,req,transport):')
assert 'with nullcontext(GOLD_OPEN)' in source
source=source.replace("'mode':'isolated-gold-main120'","'mode':'gold-ontology-on-1233'")
source=source.replace("stop.set();watcher.join(timeout=2);restore();", "stop.set();watcher.join(timeout=2);restore();GOLD_CONTEXT.__exit__(None,None,None);")
source=source.replace("put(out/'sql-errors.json',transport.errors if transport else []);print", "put(out/'sql-errors.json',transport.errors if transport else []);put(out/'resources.json',resource_samples);print")
# Use the common audited ExperimentClient, exactly one send per native ticket.
transport='''t.__class__=Authorized
 import lawrag
 lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
 from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError,ExperimentFormatError,ExperimentTransportError
 from semantic_runtime.legal_agent.local_gemma import provider_request
 from semantic_runtime.legal_agent.errors import TransportError
 audited=ExperimentClient(R,out/'experiment-client',max_calls=40,max_repairs=0)
 def reserved_send(*,body,ticket):
  audited.provider_index=ticket['provider_index'];audited._apply_provider()
  payload=provider_request(body)
  remaining=min(180,float(ticket['remaining_seconds']),float(ticket['deadline'])-time.monotonic())
  if remaining<=0:raise ContractError('reserved transport deadline exhausted')
  try:
   return super(type(audited),audited).chat_completions(payload,phase=active[-1] if active else 'request',timeout_seconds=remaining)
  except (ExperimentProviderError,ExperimentFormatError) as exc:
   if getattr(exc,'response',None) is not None:return exc.response
   raise TransportError(str(exc),retryable=False,unknown=True) from exc
  except ExperimentTransportError as exc:raise TransportError(str(exc),retryable=exc.retryable,unknown=exc.unknown) from exc
 t.send_once=reserved_send'''
source=source.replace('t.__class__=Authorized',transport)
entry='06_TOOLS/EXPERIMENTS/adr_1233/live.py';(SP/entry).parent.mkdir(parents=True);(SP/entry).write_text(source);ac.register_file(S,entry,upstream_state='absent')
ac.freeze(S);assert not ac.validate(S),ac.validate(S)
revision=read(S/'candidate.json')['revisions'][-1];F=S/'revisions'/revision['revision_id']/'snapshot'
put(D/'candidate.json',{'root':str(S.relative_to(R)),'snapshot':str(F.relative_to(R)),'entry':str((F/entry).relative_to(R)),'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256']})
print('Frozen',revision['revision_id'],'no models called')
