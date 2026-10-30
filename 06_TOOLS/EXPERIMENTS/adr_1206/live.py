"""Unchanged frozen DomainWorkflow, real archived inputs, Qwen authoring only."""
from common import *
import os,sqlite3,time,resource,types
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
from lawrag.research.experiment_client import ExperimentClient,ExperimentFormatError,ExperimentProviderError
from resource_guard import Guard,self_test
preflight='--preflight' in sys.argv
out=ART/('preflight-r2' if preflight else 'live')
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
w=DomainWorkflow(repo,store,actor='isolated-experiment-operator',source_reader=source,generate=None,namespace='ADR1206-only',source_snapshot=meta['generation_id'],acl_ref=digest(documents),document_ids=documents,glossary=glossary,producer_binding=f['candidate_revision']['revision_sha256'])
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
 guard.done.set();reader.close();print('PREFLIGHT_OK source units',len(sources),'raw records',len(raws),flush=True);raise SystemExit(0)
assert read(ART/'preflight-r2/binding.json')['model_calls']==0
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
def generate(prompt,context,schema):
 guard.check();remaining=min(180,context['call_budget']['absolute_deadline']-time.time(),deadline-time.monotonic())
 if remaining<=0:raise RuntimeError('frozen batch/job deadline exhausted')
 body={'model':client.model,'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(context,ensure_ascii=False)}],'temperature':0,'response_format':{'type':'json_schema','json_schema':{'name':'domain_profile','strict':True,'schema':schema}}}
 raw(out/f'input-{len(stage_receipts)+1:03d}.json',{'phase':phase,'prompt':prompt,'context':context,'schema':schema})
 before=client.calls;t=time.monotonic();row={'phase':phase,'attempt':context['call_budget']['attempt'],'physical_before':before}
 stage_receipts.append(row)
 try:
  response=client.chat_completions(body,phase=phase,timeout_seconds=remaining)
 except ExperimentFormatError as exc:
  row.update(status='INCOMPLETE_RESPONSE',physical_after=client.calls,seconds=time.monotonic()-t)
  raise AuthoringFailure('INCOMPLETE_RESPONSE',{'physical_calls':client.calls-before,'response':exc.response}) from exc
 except ExperimentProviderError as exc:
  row.update(status='PROVIDER_REJECTED',physical_after=client.calls,seconds=time.monotonic()-t)
  raise AuthoringFailure('HTTP_REJECTED',{'physical_calls':client.calls-before,'response':exc.response}) from exc
 except Exception:
  row.update(status='UNKNOWN',physical_after=client.calls,seconds=time.monotonic()-t);raise
 message=response['body_json']['choices'][0]['message']['content']
 try:value=json.loads(message)
 except (TypeError,ValueError):value={'invalid_json_text':message}
 row.update(status='RESPONSE_RECEIVED',physical_after=client.calls,seconds=time.monotonic()-t)
 raw(out/f'output-{len(stage_receipts):03d}.json',value)
 return value,{'model':client.model,'physical_calls':client.calls-before,'response_sha256':response['body_sha256'],'call_dir':str(client.output),'usage':client.usage[-1] if client.usage else None}
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
 guard.done.set();reader.close()
 leaks={name:str(module.__file__) for name,module in list(sys.modules.items()) if getattr(module,'__file__',None) and str(module.__file__).startswith(str(ROOT/'02_BACKEND')) and name.startswith(('semantic_runtime','lawrag'))}
 put(out/'execution.json',{'results':results,'calls':client.calls,'logical_generations':len(stage_receipts),'stage_receipts':stage_receipts,'usage':client.usage,'provider_switches':getattr(client,'provider_switches',[]),'seconds':time.monotonic()-started,'resource_stop':(out/'resource-stop.json').exists(),'imports_outside_candidate':leaks,'main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256'],'knowledge_approved':False,'published':False,'head':repo.head(bundle)})
 print(json.dumps({'results':[{k:v for k,v in r.items() if k not in ('observation','knowledge')} for r in results],'calls':client.calls,'seconds':time.monotonic()-started},ensure_ascii=False),flush=True)
