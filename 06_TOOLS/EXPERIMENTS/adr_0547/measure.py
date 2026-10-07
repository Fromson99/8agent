"""Explicit frozen-candidate injection; public Gemma measurements, never MAIN selection."""
import argparse, contextlib, copy, hashlib, importlib.util, json, sqlite3, subprocess, sys, time, uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0547-gemma-main-prompt-compaction-measurement'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0547/compact'
sys.path.insert(0,str(R/'02_BACKEND'))
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():raise FileExistsError(p)
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def emit(**values):print(json.dumps(values,ensure_ascii=False),flush=True)
def verify():
 d=read(A/'artifacts/frozen-design.json')
 assert sha(Path(__file__))==d['runner_sha256'],'runner drift'
 for p,h in d['input_sha256'].items():assert sha(R/p)==h,'input drift: '+p
 for p,h in read(A/'artifacts/control-code-hashes.json').items():assert sha(R/p)==h,'control code drift: '+p
 m=read(C/'candidate.json');assert sha(C/'candidate.json')==d['candidate_manifest_sha256']
 revision=next(x for x in m['revisions'] if x['revision_id']==d['revision_id'])
 assert revision['revision_sha256']==d['revision_sha256']
 for row in revision['files']:assert sha(R/row['frozen_path'])==row['snapshot_sha256'],'candidate drift'
 return d, C/'revisions'/d['revision_id']/'snapshot'
def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
 sys.modules[name]=mod;spec.loader.exec_module(mod)
 return mod
def install(snapshot,arm):
 # No runtime registry or production file is modified. Separate worker per arm.
 import semantic_runtime.legal_agent as package
 gateway=load_module('semantic_runtime.legal_agent.gateway',snapshot/'02_BACKEND/semantic_runtime/legal_agent/gateway.py')
 package.gateway=gateway
 obligations=load_module('semantic_runtime.legal_agent.question_obligations',snapshot/'02_BACKEND/semantic_runtime/legal_agent/question_obligations.py')
 package.question_obligations=obligations
 if arm=='baseline':
  old=read(A/'artifacts/baseline-prompts.json');obligations.SYSTEM=old['system'];obligations.PROMPTS=old['prompts']
  original=gateway.ModelGateway.__init__
  def initialize(self,*args,**kwargs):original(self,*args,**kwargs);self.compact=False
  gateway.ModelGateway.__init__=initialize
 bounded=load_module('semantic_runtime.legal_agent.bounded_source_session',snapshot/'02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py')
 package.bounded_source_session=bounded
 return gateway,obligations

def transport(d,out):
 from lawrag.research.experiment_client import ExperimentClient
 from lawrag.research.openrouter_legal_adapter import OpenRouterSingleSendAdapter
 from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
 validator=LocalGemmaTransport(R/d['local_grant_code_root'],R)
 assert set(validator.public_scope)==set(d['public_scope'])
 client=ExperimentClient(R,out,max_calls=d['max_physical_calls'],max_output_tokens=d['profile']['max_output_tokens'])
 class AuditedPublic(OpenRouterSingleSendAdapter):
  def __init__(self):super().__init__(client);self.binding=copy.deepcopy(validator.binding)
  @property
  def public_scope(self):return validator.public_scope
  def authorize(self,*a,**kw):return validator.authorize(*a,**kw)
  def validate_authorization(self,*a,**kw):return validator.validate_authorization(*a,**kw)
  def validate_model(self):return validator.validate_model()
 return AuditedPublic(),client

def journal_result(path):
 db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 run=db.execute('select * from run').fetchone();rows=db.execute('select a.*,v.phase from model_attempt a join model_view v using(view_id) order by a.created_seq').fetchall()
 calls=[]
 for row in rows:
  request=json.loads(row['request_json']);data=json.loads(request['messages'][1]['content']);stage=data['view'].get('source_stage',row['phase']);receipt=json.loads(row['receipt_json'] or '{}');usage=receipt.get('usage') or {}
  duration=(datetime.fromisoformat(row['finished_at'])-datetime.fromisoformat(row['started_at'])).total_seconds() if row['finished_at'] else None
  calls.append({'phase':stage,'status':row['status'],'seconds':duration,'input_tokens':usage.get('prompt_tokens'),'output_tokens':usage.get('completion_tokens'),'cost_usd':usage.get('cost'),'cached_tokens':(usage.get('prompt_tokens_details') or {}).get('cached_tokens'),'reasoning_tokens':(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),'request_bytes':len(row['request_json'].encode()),'system_chars':len(request['messages'][0]['content']),'user_chars':len(request['messages'][1]['content'])})
 events={row[0]:row[1] for row in db.execute('select kind,count(*) from event group by kind')}
 result={'journal':str(Path(path).relative_to(R)),'run_id':run['run_id'],'run_status':run['status'],'calls':calls,'schema_repairs':events.get('OUTPUT_SCHEMA_INVALID',0),'workflow_repairs':events.get('WORKFLOW_REPAIR',0),'input_tokens':sum(c['input_tokens'] or 0 for c in calls),'output_tokens':sum(c['output_tokens'] or 0 for c in calls),'model_seconds':sum(c['seconds'] or 0 for c in calls),'cost_usd':sum(c['cost_usd'] or 0 for c in calls)}
 db.close();return result

def e2e(d,snapshot,case,arm,out):
 install(snapshot,arm)
 from semantic_runtime.app import create_app
 from semantic_runtime.legal_agent.workflow_tiers_policy import profile
 from fastapi.testclient import TestClient
 t,client=transport(d,out/'model')
 p=profile({**d['profile'],'model_binding':t.binding},require_model=True)
 app=create_app(out,R/d['generation'],contracts_root=R,workspace_root=R,runtime_root=out/'runtime',provider=object(),implementation='legal-agent-tools-v5',legal_agent_profile=p,legal_agent_transport=t,release={'mode':'research-only','experiment_id':d['experiment_id'],'arm':arm})
 body={'question':case['question'],'document_ids':d['public_scope'],'public_question':True,'use_llm':True}
 write(out/'http-request.json',body)
 with TestClient(app,raise_server_exceptions=False) as http:
  start=time.perf_counter();response=http.post('/v1/rag/ask',json=body);elapsed=time.perf_counter()-start
  try:value=response.json()
  except ValueError:value={'non_json_response':response.text[:500]}
  write(out/'http-response.json',value)
  journals=list((out/'runtime/legal-agent/runs').glob('*/*/journal.sqlite'))
  row=journal_result(journals[0]) if journals else {'calls':[]}
  answer=value.get('answer') or {}
  row.update(mode='e2e',case_id=case['case_id'],arm=arm,status_code=response.status_code,total_seconds=elapsed,physical_calls=client.calls,answer_claims=len(answer.get('claims',[])),answer_chars=len(answer.get('text','')),answer_present=bool(answer.get('claims')),provider_usage=client.usage,semantic_quality='unmeasured')
  write(out/'result.json',row);emit(event='e2e.finished',case=case['case_id'],arm=arm,status=response.status_code,calls=client.calls,seconds=round(elapsed,2),input_tokens=row.get('input_tokens'),claims=row['answer_claims'],repairs=row.get('schema_repairs'))

class ReplayRepository:
 def __init__(self,view,gateway,out):self.view=view;self.gateway=gateway;self.out=out;self.events=[];self.calls=0
 def reserve_attempt(self,view,request,*args,numbered_references=None,wire_projection=None):
  expected=numbered_references.view(view) if numbered_references else view
  if wire_projection:expected=self.gateway.compact_wire_view(expected,view['phase'])
  assert json.loads(request['messages'][1]['content'])['view']==expected
  self.calls+=1;return 'M'+uuid.uuid4().hex
 def attempt_sent(self,ident):pass
 def finish_attempt(self,*args):return 'SUCCEEDED'
 @contextlib.contextmanager
 def transaction(self):yield
 def event(self,kind,data):self.events.append({'kind':kind,'payload':data})

def fixed(d,snapshot,case,arm,phase,repeat,out):
 gateway,obligations=install(snapshot,arm)
 frozen=read(A/'artifacts/fixed-views'/case['case_id']/(phase+'.json'))
 assert sha(A/'artifacts/fixed-views'/case['case_id']/(phase+'.json'))==read(A/'artifacts/fixed-view-hashes.json')[case['case_id']][phase]
 t,client=transport(d,out/'model')
 deadline=time.monotonic()+600
 context=SimpleNamespace(binding=frozen['binding'],request=frozen['request'],query={'scope':frozen['binding']['scope']},run_id='replay-'+uuid.uuid4().hex,remaining=lambda:max(.001,deadline-time.monotonic()))
 repo=ReplayRepository(frozen['view'],gateway,out)
 p={**d['profile'],'model_binding':t.binding}
 g=gateway.ModelGateway(repo,context,p,frozen['domain'],t,message_protocol=__import__('semantic_runtime.legal_agent.obligation_protocol',fromlist=['schema']),system=obligations.SYSTEM,prompts=obligations.PROMPTS)
 name='Draft' if phase=='compose' else 'ReviewDecision';start=time.perf_counter();error=None;result=None
 try:result=g.generate(phase,frozen['view'],name)
 except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)[:500]}
 elapsed=time.perf_counter()-start
 if result is not None:write(out/'output.json',result)
 write(out/'events.json',repo.events)
 quotation_checks=[]
 if phase=='review' and result:
  texts={e['evidence']:e['text'] for e in frozen['view']['exact_evidence']}
  for check in result['checks']:
   for source in check.get('source_checks',[]):quotation_checks.append({'source':source['source'],'quote_in_delivered_source':source['quote'] in texts.get(source['source'],''),'draft_quote_in_claim':any(source['draft_quote'] in c['text'] for c in frozen['view'].get('claims',[]))})
 row={'mode':'fixed','case_id':case['case_id'],'arm':arm,'phase':phase,'repeat':repeat,'physical_calls':client.calls,'total_seconds':elapsed,'provider_usage':client.usage,'input_tokens':sum(x.get('input_tokens') or 0 for x in client.usage),'output_tokens':sum(x.get('output_tokens') or 0 for x in client.usage),'cost_usd':sum(x.get('cost_usd') or 0 for x in client.usage),'schema_repairs':sum(x['kind']=='OUTPUT_SCHEMA_INVALID' for x in repo.events),'valid_output':result is not None,'error':error,'quotation_checks':quotation_checks,'semantic_quality':'unmeasured'}
 write(out/'result.json',row);emit(event='fixed.finished',case=case['case_id'],arm=arm,phase=phase,repeat=repeat,calls=client.calls,seconds=round(elapsed,2),input_tokens=row['input_tokens'],valid=row['valid_output'],error=error)

def freeze_views(d):
 hashes={};selections=[]
 for case_id in d['case_order']:
  hashes[case_id]={}
  for phase in d['fixed_replay_phases']:
   for arm in ['baseline','compact']:
    result=read(A/'artifacts/run-001/e2e'/case_id/arm/'result.json')
    if not result.get('journal'):continue
    db=sqlite3.connect((R/result['journal']).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    v=db.execute('select body_json from model_view where phase=? order by created_seq limit 1',(phase,)).fetchone();run=db.execute('select * from run').fetchone()
    if v:
     value={'view':json.loads(v[0]),'binding':json.loads(run['binding_json']),'request':json.loads(run['request_json']),'domain':read(R/'00_SYSTEM/LEGAL_AGENT/domain-v5.json'),'provenance':{'arm':arm,'journal':result['journal'],'phase':phase,'rule':d['fixed_view_rule']}}
     ids={e.get('document_id') for e in value['view'].get('exact_evidence',[]) if e.get('document_id')};assert ids.issubset(set(d['public_scope']))
     path=A/'artifacts/fixed-views'/case_id/(phase+'.json');write(path,value);hashes[case_id][phase]=sha(path);selections.append({'case':case_id,'phase':phase,'arm':arm,'evidence_cards':len(value['view'].get('exact_evidence',[]))});db.close();break
    db.close()
 write(A/'artifacts/fixed-view-hashes.json',hashes);write(A/'artifacts/fixed-view-provenance.json',selections)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=['e2e','fixed']);parser.add_argument('--arm');parser.add_argument('--case');parser.add_argument('--phase');parser.add_argument('--repeat',type=int,default=1);parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
 d,snapshot=verify();cases=read(R/d['product_cases'])['cases'];by_id={c['case_id']:c for c in cases}
 if args.preflight:
  from semantic_runtime.storage import Store
  t,_=transport(d,A/'artifacts/preflight-client');store=Store(R/d['generation'])
  assert store.manifest['store_sha256']==read(A/'artifacts/public-grant.json')['source_store_sha256'] and store.manifest['export_allowed'] is False
  t.authorize({'scope':{'document_version_ids':d['public_scope']}},{'use_llm':True},store.manifest,public_question=True)
  store.close();emit(event='preflight.passed',model=d['model'],public_docs=len(d['public_scope']),network_calls=0);return
 if args.worker:
  out=A/'artifacts/run-001'/args.worker/args.case/(args.arm if args.worker=='e2e' else args.phase+'/repeat-'+str(args.repeat)+'/'+args.arm)
  if args.worker=='e2e':e2e(d,snapshot,by_id[args.case],args.arm,out)
  else:fixed(d,snapshot,by_id[args.case],args.arm,args.phase,args.repeat,out)
  return
 count=0
 for cid in d['case_order']:
  for arm in d['e2e_arm_order'][cid]:
   subprocess.run([sys.executable,str(Path(__file__)),'--worker','e2e','--case',cid,'--arm',arm],cwd=R,check=True)
   count+=read(A/'artifacts/run-001/e2e'/cid/arm/'result.json')['physical_calls'];assert count<=d['max_physical_calls']
 freeze_views(d)
 hashes=read(A/'artifacts/fixed-view-hashes.json')
 for phase,repeats in d['fixed_replay_phases'].items():
  for index,cid in enumerate(d['case_order']):
   if phase not in hashes[cid]:emit(event='fixed.unmeasured',case=cid,phase=phase,reason='no actual phase view');continue
   for repeat in range(1,repeats+1):
    order=['baseline','compact'] if (index+repeat+(phase=='review'))%2 else ['compact','baseline']
    for arm in order:
     subprocess.run([sys.executable,str(Path(__file__)),'--worker','fixed','--case',cid,'--arm',arm,'--phase',phase,'--repeat',str(repeat)],cwd=R,check=True)
     row=read(A/'artifacts/run-001/fixed'/cid/phase/('repeat-'+str(repeat))/arm/'result.json');count+=row['physical_calls'];assert count<=d['max_physical_calls']
 rows=[read(p) for p in (A/'artifacts/run-001').glob('**/result.json')]
 write(A/'artifacts/run-001/result.json',{'experiment_id':d['experiment_id'],'status':'complete','physical_calls':count,'rows':rows,'main_wiring_unchanged':True,'semantic_quality':'unmeasured'})
 emit(event='measurement.finished',physical_calls=count,results=len(rows))
if __name__=='__main__':main()
