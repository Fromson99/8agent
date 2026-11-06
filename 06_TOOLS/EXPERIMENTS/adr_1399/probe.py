"""Actual Qwen diagnostic/primary calls on controlled faults, no answer keys."""
from common import *
import time,traceback,base64
from copy import deepcopy
os.environ.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2',PYTHONDONTWRITEBYTECODE='1',LAWRAG_WORKSPACE_ROOT=str(ROOT))
candidate=read(DES/'candidate-repaired.json');C=ROOT/candidate['code_root']
assert all(sha(C/n)==h for n,h in candidate['selected_files'].items())
for p,h in read(DES/'freeze-public.json')['files'].items():assert sha(ROOT/p)==h,p
if (ART/'STOP_EXTERNAL.json').exists():raise RuntimeError('Prior uncertain outcome; no new send')
from pinned_imports import install,verify_loaded
install(ART/'transport')
import lawrag,lawrag.core,lawrag.research
for pkg,path in [(lawrag,'02_BACKEND/lawrag'),(lawrag.core,'02_BACKEND/lawrag/core'),(lawrag.research,'02_BACKEND/lawrag/research')]:pkg.__path__.extend([str(C/path),str(ROOT/path)])
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT)]
from semantic_runtime.legal_agent import reason_decision_review as review,output_contract as output
from semantic_runtime.legal_agent.context import RequestContext
from semantic_runtime.legal_agent.repository import WorkRepository
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.contracts import digest
from lawrag.research.experiment_client import ExperimentClient
from lawrag.research.openrouter_legal_adapter import send_reserved
from lawrag.core import request_deadline
verify_loaded(ART/'transport')
cases=read(DES/'probe-cases.json');criteria=read(DES/'criteria.json')
if '--preflight' in sys.argv:
 for case in cases:output.validate_shape(case['proposal'],case['schema'])
 assert len(cases)==12 and len(criteria['repair_case_ids'])==5
 print('PROBE_PREFLIGHT',len(cases),'schemas; pinned transport; no model calls',flush=True);sys.exit(0)
base=ART/'probes';base.mkdir(exist_ok=False)
from resource_guard import Guard
guard=Guard(base);guard.start()
client=ExperimentClient(ROOT,base/'experiment-client',max_calls=22,max_repairs=0,provider_policy=DES/'provider-policy.json')
calls=[];results=[];repair_results=[];phase=['none'];active_case=['none'];logical=0;repos={};original_post=request_deadline.post_json
def gz(path,value):write_raw_json(path,value)
def post(url,**kwargs):
 guard.check();verify_loaded(ART/'transport')
 if (ART/'STOP_EXTERNAL.json').exists():raise RuntimeError('GLOBAL_STOP_NO_SEND')
 if len(calls)>=22:raise RuntimeError('Frozen probe22 physical budget')
 if sum((c.get('usage') or {}).get('cost',0) or 0 for c in calls)>=3:raise RuntimeError('Reported USD3 stop')
 payload=kwargs['json_body'];assert payload['model']=='qwen/qwen3.8-27b' and payload['reasoning']=={'effort':'none'}
 assert payload['provider']['only']==['parasail/fp8']
 assert not any(k in payload for k in ('max_tokens','max_output_tokens','max_completion_tokens'))
 row={'number':len(calls)+1,'case_id':active_case[0],'stage':phase[0],'status':'started'};calls.append(row)
 out=base/'raw'/f'call-{row["number"]:03d}';out.mkdir(parents=True,exist_ok=False);gz(out/'request.json.gz',payload);put(base/'calls.json',calls)
 start=time.monotonic();print('MODEL',row['number'],row['case_id'],row['stage'],flush=True)
 try:
  response=original_post(url,**kwargs)
  try:raw=response.json()
  except ValueError:raw={'non_json_body':response.text}
  gz(out/'response.json.gz',raw)
  row.update(status='unknown' if response.status_code>=500 else 'responded',http_status=response.status_code,usage=raw.get('usage'),actual_provider=raw.get('provider'),actual_model=raw.get('model'),transport_diagnostics=response.extensions.get('absolute_deadline',{}))
  if row['status']=='unknown':put(ART/'STOP_EXTERNAL.json',{'call':row,'reason':'remote5xx; no further external sends'})
  return response
 except Exception as exc:
  row.update(status='unknown',error_type=type(exc).__name__,transport_diagnostics=getattr(exc,'diagnostics',{}))
  if hasattr(exc,'partial_body'):gz(out/'partial.json.gz',{'body_base64':base64.b64encode(exc.partial_body).decode(),'diagnostics':getattr(exc,'diagnostics',{})})
  put(ART/'STOP_EXTERNAL.json',{'call':row,'reason':'Unconfirmed physical outcome; no retry'})
  raise
 finally:
  row['seconds']=time.monotonic()-start;put(out/'finished.json',row);put(base/'calls.json',calls)
request_deadline.post_json=post
def invoke(prompt,body,schema,kind):
 global logical
 logical+=1;phase[0]=kind;deadline=repos[active_case[0]].context.remaining()
 wire=provider_request({'model':'qwen/qwen3.8-27b','temperature':0,'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(body,ensure_ascii=False)}],
   'response_format':{'type':'json_schema','json_schema':{'name':'ReasonDecision','strict':True,'schema':deepcopy(schema)}}})
 gz(base/'canonical'/f'{logical:03d}.json.gz',{'case_id':active_case[0],'phase':kind,'system':prompt,'body':body,'validation_schema':schema})
 raw=client.chat_completions(wire,phase=kind,timeout_seconds=min(180,deadline))
 try:value=json.loads(raw['body_json']['choices'][0]['message']['content'])
 except (ValueError,KeyError,IndexError,TypeError) as exc:raise output.OutputContractError('Invalid complete JSON') from exc
 gz(base/'canonical'/f'{logical:03d}-output.json.gz',value)
 return value
def check(case,value):
 output.validate_shape(value,case['schema'])
 return review.review(repos[case['id']],stage=case['stage'],context=case['context'],proposal=value,
  binding={'code':candidate['pin']['revision_sha256'],'case':case['id'],'source':digest(case['context'])},
  invoke=lambda p,b,s:invoke(p,b,s,'common-review'))
try:
 for case in cases:
  if (ART/'STOP_EXTERNAL.json').exists():break
  active_case[0]=case['id'];request={'question':case['context'].get('current_request',case['context'].get('request','새 판단을 기존 지식과 비교한다.'))}
  context=RequestContext.create({'id':case['id'],**request},request,{'case_id':case['id'],'code':candidate['pin']['revision_sha256']},600)
  repo=WorkRepository(base/case['id']/'journal.sqlite',context,{'max_model_attempts':4,'finalization_reserve':0,'max_tool_actions':1});repos[case['id']]=repo
  before=len(calls);start=time.monotonic();row={'case_id':case['id'],'group':case['group'],'stage':case['stage'],'seeded_proposal':True}
  try:
   receipt=check(case,case['proposal']);row.update(outcome='PASS',receipt=receipt)
  except review.ReviewConflict as exc:row.update(outcome='REPAIR',receipt=exc.review_receipt)
  except Exception as exc:row.update(outcome='FAILURE',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
  row.update(seconds=time.monotonic()-start,physical_calls=len(calls)-before)
  if row['outcome'] in ('PASS','REPAIR'):
   before_reuse=len(calls)
   try:check(case,case['proposal'])
   except review.ReviewConflict:pass
   row['duplicate_extra_calls']=len(calls)-before_reuse;assert row['duplicate_extra_calls']==0
  results.append(row);put(base/'results.json',results);print('PROBE_RESULT',case['id'],row['outcome'],flush=True)
 for case in cases:
  if (ART/'STOP_EXTERNAL.json').exists():break
  if case['id'] not in criteria['repair_case_ids']:continue
  initial=next((r for r in results if r['case_id']==case['id']),None)
  if not initial or initial['outcome']!='REPAIR':
   repair_results.append({'case_id':case['id'],'status':'NOT_ATTEMPTED','reason':'Initial reviewer did not produce valid REPAIR'});continue
  active_case[0]=case['id'];before=len(calls);start=time.monotonic();repo=repos[case['id']]
  # The fixed input is an explicit injected fault. Subsequent primary and
  # reviewer outputs are all fresh Qwen; no expected answer enters this body.
  def primary(payload,attempt):
   if not attempt:return deepcopy(case['proposal'])
   return invoke('당신은 원래 판단을 제출한 담당자다. '+review.RECONSIDER+' 현재 context의 사실과 원문을 보고 스키마에 맞는 전체 제안을 반환한다.',payload,case['schema'],'primary-reconsider')
  row={'case_id':case['id'],'boundary_execution_only':True}
  try:
   accepted=output.bounded_decision(repo,'boundary-primary',{'context':case['context']},case['schema'],primary,lambda v:check(case,v),identity={'case':case['id'],'version':review.VERSION})
   execution={'case_id':case['id'],'accepted_proposal':accepted,'proposal_hash':digest(accepted),'code':candidate['pin']['revision_sha256'],'not_a_real_source_tool':True}
   repo.event('PROBE_ACCEPTED_EXECUTION',execution);put(base/case['id']/'accepted-execution.json',execution)
   count=len(calls);again=output.bounded_decision(repo,'boundary-primary',{'context':case['context']},case['schema'],primary,lambda v:check(case,v),identity={'case':case['id'],'version':review.VERSION});assert again==accepted and len(calls)==count
   row.update(status='ACCEPTED',accepted=accepted,duplicate_extra_calls=0)
  except Exception as exc:row.update(status='REJECTED',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
  row.update(seconds=time.monotonic()-start,physical_calls=len(calls)-before);repair_results.append(row);put(base/'repairs.json',repair_results);print('REPAIR_RESULT',case['id'],row['status'],flush=True)
finally:
 put(base/'results.json',results);put(base/'repairs.json',repair_results);put(base/'calls.json',calls)
 for repo in repos.values():repo.close()
 guard.done.set();guard.thread.join(2)
 request_deadline.post_json=original_post
 print('PROBES_DONE',len(results),len(calls),'unknown',sum(c['status']=='unknown' for c in calls),flush=True)
