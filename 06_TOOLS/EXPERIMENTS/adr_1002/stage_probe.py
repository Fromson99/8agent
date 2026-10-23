"""One exact navigation-stage call, no adaptive retry or evaluator context."""
from common import *
import sys,time,traceback
from types import SimpleNamespace as S
from copy import deepcopy
arm,case_id=sys.argv[1:];s=read(ART/'stage.json');f=read(ART/'design-freeze.json');C=ROOT/s['roots'][arm]
assert sha(ART/'stage-inputs.json')==f['stage_inputs_sha256']
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
if arm=='candidate':assert all(sha(C/n)==h for n,h in f['files']['candidate'].items())
else:assert all(sha(C/n)==h for n,h in s['base_release']['files'].items())
from stop_policy import StopPolicy
stop=StopPolicy(ART/'stop.json',20);stop.before_call(0)
out=ART/'paired'/case_id/arm;out.mkdir(parents=True,exist_ok=False)
sys.path[:0]=[str(C/'02_BACKEND'),str(ROOT/'02_BACKEND')]
import lawrag;lawrag.__path__.append(str(ROOT/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentClient,ExperimentProviderError,ExperimentTransportError
from semantic_runtime.legal_agent import decision_projection as dp,law_navigation as nav,output_contract as oc,investigation_scope as scope
from semantic_runtime.legal_agent.local_gemma import provider_request
from jsonschema import validate
client=ExperimentClient(ROOT,out/'model',max_calls=1)
row=next(r for r in read(ART/'stage-inputs.json') if r['id']==case_id);d=row['data'];a=row['actions']
events=[]
def check(v,d,a):validate(v,nav.decision_schema(d,a,set()));scope.validate(v,d)
inv=S(modern=True,control=False,policy={'answer_progress_control':arm=='candidate'},p={'binding':{'synthetic':'stage-v1'}},s=S(repo=S(budget=lambda:dict(model_limit=40,model_reserved=0,finalization_reserve=3),event=lambda *x:events.append(x))),question=row['question'],save=lambda:None,validate=check,left=lambda:180)
if row['prior_opinion']:
 prior={'choice':'READ','selections':[{'target':'previous','issue_id':'Q1','missing_need':'제2조 지급 항목 확인','relation':'DEPENDENCY','source_ref':'E1'}]}
 inv.p['executed_compact_choices']=[deepcopy(prior)]
 if arm=='candidate':
  from semantic_runtime.legal_agent import answer_progress as ap
  prior['answer_progress']={'status':'NEEDS_SOURCE','answer_so_far':'경비 항목은 제2조에 위임되어 있다.','basis_refs':['E1'],'material_need':'국내 출장 경비 항목','next_answer_change':'위임된 지급 항목을 알 수 있다.','previous_effect':'INITIAL'}
  ap.record(inv,d,prior,'synthetic-prior-opinion')
def invoke(system,payload,schema,phase,timeout):
 save(out/'stage-request.json',{'system':system,'view':payload,'schema':schema})
 body={'model':client.model,'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps({'view':payload},ensure_ascii=False)}],'temperature':0,'max_tokens':6400,'response_format':{'type':'json_schema','json_schema':{'name':'navigation_choice','strict':True,'schema':schema}}}
 response=client.chat_completions(provider_request(body),phase='stage-probe',timeout_seconds=timeout)
 value=json.loads(response['choices'][0]['message']['content']);save(out/'proposal.json',value);return value
inv.invoke=invoke
original=oc.bounded_decision
def one_call(repo,name,payload,schema,invoke,check,**kw):
 value=invoke(payload,0);check(value);return value
oc.bounded_decision=one_call
start=time.monotonic();result={'arm':arm,'case_id':case_id,'stage_only':True,'error':None}
try:result['decision']=dp.choose_read(inv,d,a,'source-law-navigation')
except (ExperimentProviderError,ExperimentTransportError) as exc:
 stop.stop(type(exc).__name__,client.calls,(getattr(exc,'response',None) or {}).get('status_code'))
 result['error']={'type':type(exc).__name__,'message':str(exc)}
except Exception as exc:result['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
finally:
 oc.bounded_decision=original
 result.update(model_calls=client.calls,seconds=time.monotonic()-start,usage=client.usage,events=events)
 save(out/'result.json',result)
print(json.dumps({'arm':arm,'case':case_id,'calls':client.calls,'error':result['error'],'action':result.get('decision',{}).get('next_action')},ensure_ascii=False))
if (ART/'stop.json').exists():raise SystemExit(2)
