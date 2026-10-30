"""Unchanged frozen DomainWorkflow, real archived inputs, Qwen authoring only."""
from common import *
import os,sqlite3,time,resource,types,httpx
from unittest.mock import patch
from copy import deepcopy
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
f=read(DES/'freeze.json');C=ROOT/f['code_root']
for p,h in f['files'].items():assert sha(C/p)==h,p
for p,h in f['inputs'].items():assert sha(ROOT/p)==h,p
for p,h in f['scripts'].items():assert sha(ROOT/p)==h,p
for name in ('ontology-domain-profile-v1.schema.json','ontology-business-profile-v1.schema.json'):
 assert sha(ROOT/'00_SYSTEM/SCHEMAS'/name)==sha(C/'00_SYSTEM/SCHEMAS'/name)
os.environ.update(LAWRAG_WORKSPACE_ROOT=str(ROOT),LAWRAG_TOOL_WORKSPACE_ROOT=str(ROOT),MALLOC_ARENA_MAX='1')
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.full_glossary import Glossary
from semantic_runtime.full_glossary_connections import ConnectionReader
from semantic_runtime.ontology_work.glossary_binding import GlossaryBinding
from semantic_runtime.ontology_work.repository import Repository
from semantic_runtime.ontology_work.store import LocalFolderStore
from semantic_runtime.ontology_work.domain_workflow import DomainWorkflow
from semantic_runtime.ontology_work.configuration import source_reader
from semantic_runtime.ontology_work.observations import envelope
from semantic_runtime.contracts import digest
from semantic_runtime.ontology_work.authoring_model import AuthoringFailure
from semantic_runtime.ontology_work import authoring_model,profile_schema
from semantic_runtime.legal_agent.wire_schema import project_request
from semantic_runtime import genos
from lawrag.core import request_deadline as dt
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError
from resource_guard import Guard,self_test
preflight='--preflight' in sys.argv
out=ART/('preflight' if preflight else 'live')
out.mkdir(parents=True,exist_ok=False)
guard=Guard(out);guard.start();assert self_test()==8
baseline=read(DES/'baseline.json');data=ROOT/baseline['data_path'];meta=baseline['data_binding'];g=meta['glossary']
assert sha(data/'manifest.json')==baseline['generation_manifest_sha256']
reader=Glossary(data/g['bundle'],data/g['dictionary'],data/g['cache'],manifest_sha256=g['manifest_sha256'],connection_factory=ConnectionReader)
glossary=GlossaryBinding(reader,snapshot=meta['generation_id']);sources=read(DES/'originals.json');cases=read(DES/'cases.json')
documents=sorted({s['anchor']['document_id'] for s in sources})
repo=Repository(lambda:sqlite3.connect(out/'work.sqlite'));repo.initialize();store=LocalFolderStore(out/'objects')
source=source_reader({'environment':'local','source':{'kind':'sqlite-local','path':str(data/'store.sqlite')}},documents)
for s in sources:assert source(s['anchor'])==s['text']
w=DomainWorkflow(repo,store,actor='isolated-experiment-operator',source_reader=source,generate=None,namespace='ADR1226-only',source_snapshot=meta['generation_id'],acl_ref=digest(documents),document_ids=documents,glossary=glossary,producer_binding=f['candidate_revision']['revision_sha256'])
p=w.save_profile(read(C/'00_SYSTEM/ONTOLOGY_PROFILES/domain-profile-v1.json'),read(C/'00_SYSTEM/ONTOLOGY_PROFILES/business-profile-v1.json'))
w.review_profile(p['bundle_id'],p['revision'],p['work_hash'],True,'isolated experimental profile, not legal knowledge approval')
raws=[]
for i,c in enumerate(cases):
 original=read(ROOT/c['origin']['path'])
 for key in c['origin']['pointer'].strip('/').split('/'):original=original[int(key)] if isinstance(original,list) else original[key]
 assert original==c['payload']
 e=envelope(original,namespace=w.namespace,run_id=c['id'],event_id=c['origin']['path']+c['origin']['pointer'],sequence=i,source_snapshot=w.source_snapshot,producer_binding=c['origin']['sha256'],acl_ref=w.acl_ref,document_ids=documents,format_description='Exact archived canonical-output subtree: '+c['origin']['pointer'],origin='ARCHIVED_MODEL_OUTPUT')
 raws.append(w.ingest(e))
 checks=glossary.candidates(c['labels']);glossary.verify_candidates(checks)
 raw(out/(c['id']+'-glossary.json'),checks)
put(out/'binding.json',{'candidate':f['candidate_revision'],'profile':p,'glossary':glossary.binding,'raws':raws,'source_ids':[s['id'] for s in sources],'source_chars':sum(len(s['text']) for s in sources),'operator':'isolated-experiment-operator','profile_only_approved':True,'knowledge_approval':False,'generation':meta['generation_id'],'model_calls':0})
if preflight:
 # The exact selected authoring generator must reach its real last-wire boundary.
 captured=[]
 endpoint=types.SimpleNamespace(headers={},url=lambda path:'https://authoring-experiment.invalid'+path)
 def capture(url,**kw):
  captured.append(deepcopy(kw['json_body']));return httpx.Response(429,text='synthetic preflight refusal; no network')
 checks=[];compiled=w.selected_profile(p['bundle_id'],p['work_hash'])
 with patch.object(genos,'from_env',lambda kind:(endpoint,'synthetic')),patch.object(genos,'advertised_model',lambda *a:'synthetic'),patch.object(dt,'post_json',capture):
  for name in ('output_schema','accumulation_schema'):
   schema=compiled[name]
   if name=='accumulation_schema':
    from semantic_runtime.ontology_work.accumulation import accumulation_schema
    schema=accumulation_schema(compiled,[],originals=[s for s in sources if s['id'] in cases[0]['original_ids']])
   if name=='output_schema':
    from semantic_runtime.ontology_work.observations import normalization_schema
    schema=normalization_schema(w.load(raws[0]['bundle_id'])['raw'],compiled)
   before=deepcopy(schema)
   try:authoring_model.generate(store,'preflight',{'call_budget':{'absolute_deadline':time.time()+30}},schema)
   except AuthoringFailure as exc:assert exc.status=='HTTP_REJECTED'
   else:raise AssertionError('synthetic refusal accepted')
   body=captured[-1];expected,receipt=project_request({'response_format':{'json_schema':{'schema':schema}}})
   assert body['response_format']['json_schema']['schema']==expected['response_format']['json_schema']['schema']
   assert schema==before and body['response_format']['json_schema']['strict'] is True
   assert not {'max_tokens','max_completion_tokens','max_output_tokens'}&body.keys()
   checks.append({'stage':name,**receipt,'actual_authoring_boundary':True})
 put(out/'transport-checks.json',{'checks':checks,'external_model_calls':0,'synthetic_refusals':2})
 guard.done.set();guard.thread.join(timeout=2);reader.close();print('PREFLIGHT_OK source units',len(sources),'raw records',len(raws),'actual authoring schemas',[(r['stage'],r['wire_schema_chars']) for r in checks],flush=True);raise SystemExit(0)
assert read(ART/'preflight/binding.json')['model_calls']==0
for n in ('00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'):assert sha(ROOT/n)==sha(C/n)
client=ExperimentClient(ROOT,out/'calls',max_calls=9,max_repairs=0,schema_in_prompt=False)
# Only serialization changes: preserve exact request/response content as lossless gzip.
def compressed_write(self,path,value):
 path=Path(path)
 if self._key in json.dumps(value,ensure_ascii=False):raise RuntimeError('credential detected in artifact')
 if path.exists():path=path.with_name(path.stem+'-'+str(self.calls)+'.json')
 raw(path,value)
client._write=types.MethodType(compressed_write,client)
started=time.monotonic();deadline=started+1800;phase='unassigned';stage_receipts=[];stop=False
put(out/'dispatch.json',{'started_epoch':time.time(),'maximum_physical_calls':9,'deadline_seconds':1800,'user_authorized':True})
original_post=dt.post_json
endpoint=types.SimpleNamespace(headers={},url=lambda path:'https://authoring-experiment.invalid'+path)
def bridged_post(url,**kw):
 guard.check()
 if not url.startswith('https://authoring-experiment.invalid/'):
  # ExperimentClient owns authentication, policy, exact external request and deadline.
  return original_post(url,**kw)
 body=kw['json_body'];raw(out/f'wire-{len(stage_receipts):03d}.json',body)
 remaining=min(180,kw['deadline']-time.monotonic(),deadline-time.monotonic())
 if remaining<=0:raise RuntimeError('frozen batch/job deadline exhausted')
 try:response=client.chat_completions(body,phase=phase,timeout_seconds=remaining)
 except ExperimentFormatError as exc:
  raise AuthoringFailure('INCOMPLETE_RESPONSE',{'physical_calls':client.calls-stage_receipts[-1]['physical_before'],'response':exc.response}) from exc
 except ExperimentProviderError as exc:
  raise AuthoringFailure('HTTP_REJECTED',{'physical_calls':client.calls-stage_receipts[-1]['physical_before'],'response':exc.response}) from exc
 # This envelope contains the unmodified provider JSON, consumed by product parser.
 return httpx.Response(response['status_code'],json=response['body_json'])
def generate(prompt,context,schema):
 guard.check()
 raw(out/f'input-{len(stage_receipts)+1:03d}.json',{'phase':phase,'prompt':prompt,'context':context,'schema':schema})
 before=client.calls;t=time.monotonic();row={'phase':phase,'attempt':context['call_budget']['attempt'],'physical_before':before}
 stage_receipts.append(row)
 if client.calls>=9:
  row.update(status='BUDGET_EXHAUSTED',physical_after=client.calls,seconds=0,pre_dispatch=True)
  put(out/f'stage-{len(stage_receipts):03d}.json',row)
  raise AuthoringFailure('BUDGET_EXHAUSTED',{'physical_calls':0,'pre_dispatch':True})
 print('STAGE_START',phase,'attempt',row['attempt'],flush=True)
 try:
  with patch.object(genos,'from_env',lambda kind:(endpoint,client.model)),patch.object(genos,'advertised_model',lambda *a:client.model),patch.object(dt,'post_json',bridged_post):
   value,receipt=authoring_model.generate(store,prompt,context,schema)
 except Exception as exc:
  row.update(status=exc.status if isinstance(exc,AuthoringFailure) else 'UNKNOWN',physical_after=client.calls,seconds=time.monotonic()-t)
  put(out/f'stage-{len(stage_receipts):03d}.json',row);print('STAGE_FAILURE',phase,row['status'],flush=True);raise
 row.update(status='RESPONSE_RECEIVED',physical_after=client.calls,seconds=time.monotonic()-t,schema_projection=receipt.get('schema_projection'))
 raw(out/f'output-{len(stage_receipts):03d}.json',value);put(out/f'stage-{len(stage_receipts):03d}.json',row)
 print('STAGE_RESPONSE',phase,row['seconds'],flush=True)
 return value,{**receipt,'physical_calls':client.calls-before,'external_model':client.model,'call_dir':str(client.output),'usage':client.usage[-1] if client.usage else None}
w.generate=generate;results=[];bundle='cb-kb-actual-kosdaq-acquisition';revision=0
try:
 for i,(case,raw_row) in enumerate(zip(cases,raws)):
  row={'case_id':case['id'],'normalization':'NOT_RUN','accumulation':'NOT_RUN','preview':'NOT_RUN'};results.append(row)
  if stop:continue
  phase='normalize-'+('a' if i==0 else 'b')
  try:
   result=w.normalize(raw_row['bundle_id'],profile_id=p['bundle_id'],profile_work_hash=p['work_hash'],labels=case['labels'])
   row.update(normalization='SAVED',observation=result)
   raw(out/(case['id']+'-normalized.json'),w.load(result['bundle_id']))
  except Exception as exc:
   row.update(normalization='FAILED',error_type=type(exc).__name__,error=str(exc)[:5000]);stop=any(x['status']=='UNKNOWN' for x in stage_receipts)
   put(out/(case['id']+'-status.json'),row);continue
  if i>0 and revision==0:
   row['accumulation']='NOT_RUN_DEPENDENCY';put(out/(case['id']+'-status.json'),row);continue
  phase='accumulate-'+('a' if i==0 else 'b')
  try:
   result=w.accumulate(bundle_id=bundle,expected_revision=revision,profile_id=p['bundle_id'],profile_work_hash=p['work_hash'],observation_ids=[row['observation']['bundle_id']],originals=[s for s in sources if s['id'] in case['original_ids']])
   revision=result['revision'];row.update(accumulation='DRAFT_SAVED',knowledge=result)
   raw(out/(case['id']+'-knowledge.json'),w.load(bundle))
   preview=w.preview(bundle);raw(out/(case['id']+'-preview.json'),preview)
   row.update(preview='COMPILED',nodes=len(preview['graph']['nodes']),paths=len(preview['paths']))
  except Exception as exc:
   row.update(accumulation='FAILED',error_type=type(exc).__name__,error=str(exc)[:5000]);stop=any(x['status']=='UNKNOWN' for x in stage_receipts)
  put(out/(case['id']+'-status.json'),row)
finally:
 guard.done.set();guard.thread.join(timeout=2);reader.close()
 leaks={name:str(module.__file__) for name,module in list(sys.modules.items()) if getattr(module,'__file__',None) and name.startswith(('semantic_runtime','lawrag')) and not Path(module.__file__).resolve().is_relative_to(C)}
 put(out/'execution.json',{'results':results,'calls':client.calls,'logical_generations':len(stage_receipts),'stage_receipts':stage_receipts,'usage':client.usage,'provider_switches':getattr(client,'provider_switches',[]),'seconds':time.monotonic()-started,'resource_stop':(out/'resource-stop.json').exists(),'imports_outside_candidate':leaks,'main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256'],'knowledge_approved':False,'published':False,'head':repo.head(bundle),'serving487_unchanged':all(sha(ROOT/n)==h for n,h in baseline['release']['files'].items()),'candidate487_exact':all(sha(C/n)==h for n,h in f['files'].items())})
 print(json.dumps({'results':[{k:v for k,v in r.items() if k not in ('observation','knowledge')} for r in results],'calls':client.calls,'seconds':time.monotonic()-started},ensure_ascii=False),flush=True)
