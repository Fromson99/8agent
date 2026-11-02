from pathlib import Path
from types import SimpleNamespace as S
import ast,json,sys,sqlite3
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1235-gold-ontology-transport-live';D=A/'artifacts/design';O=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
C=R/read(R/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/binding.json')['engine_root'];sys.path[:0]=[str(C/'02_BACKEND'),str(C)];import lawrag;lawrag.__path__.append(str(R/'02_BACKEND/lawrag'))
from lawrag.research.experiment_client import ExperimentProviderError,ExperimentFormatError
from semantic_runtime.legal_agent.errors import TransportError,ContractError
from semantic_runtime.legal_agent import provider_routing as routing
from semantic_runtime.contracts import digest
entry=R/read(D/'candidate.json')['entry'];fn=next(n for n in ast.parse(entry.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='preserve_provider_failure');ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(entry),'exec'),ns);failure=ns['preserve_provider_failure'];rows=[]
for status in (429,503,401):
 response={'status_code':status,'body_json':{'error':{'code':status}},'body_sha256':digest(status)}
 try:failure(ExperimentProviderError('synthetic',response=response,retryable=True));raise AssertionError('not raised')
 except TransportError as exc:
  assert exc.retryable==(status==429) and exc.unknown==(status>=500) and exc.response['status_code']==status
  if status==429:rejected=exc.response
 rows.append({'test':'native_error_'+str(status),'status':'passed'})
try:failure(ExperimentProviderError('no response'));raise AssertionError()
except TransportError as e:assert e.unknown and not e.retryable
rows.append({'test':'missing_response_unknown','status':'passed'})
try:failure(ExperimentProviderError('policy',response={'status_code':200}));raise AssertionError()
except ContractError:pass
rows.append({'test':'successful_http_policy_error_rejected','status':'passed'})
r={'status_code':200,'body_json':{'model':'qwen/qwen3.8-27b','choices':[{'finish_reason':'error','message':{'content':None}}]}}
assert failure(ExperimentFormatError('incomplete',response=r))==r;rows.append({'test':'format_raw_preserved_for_native_validator','status':'passed'})
db=sqlite3.connect(':memory:');db.execute('create table event(seq integer primary key, kind text,payload_json text,payload_hash text)')
def event(k,v):db.execute('insert into event(kind,payload_json,payload_hash) values(?,?,?)',(k,json.dumps(v),digest(v)))
repo=S(db=db,event=event);policy=read(R/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json');routing.validate_policy(policy)
assert routing.switch(repo,policy,digest(policy),'binding','attempt1',rejected)
assert not routing.switch(repo,policy,digest(policy),'binding','attempt2',rejected)
assert not routing.switch(repo,policy,digest(policy),'binding','attempt3',{'status_code':503,'acceptance':'UNKNOWN'})
assert routing.current(repo,policy,digest(policy),'binding')[0]['switches']==1
rows.append({'test':'native_gateway_policy_one_known429_switch_only','status':'passed'});db.close()
(O/'checks.json').write_text(json.dumps({'passed':len(rows),'failed':0,'rows':rows,'models':0},indent=2)+'\n');print(len(rows),'passed')
