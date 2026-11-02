from pathlib import Path
import json,sys,ast,tempfile,threading,time,io,os
sys.dont_write_bytecode=True
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1258-main129-fixed-cap-oracle-live';D=A/'artifacts/design';O=A/'artifacts/run-001';read=lambda p:json.loads(p.read_text());F=R/read(D/'candidate.json')['snapshot'];C=R/read(D/'before.json')['binding']['engine_root'];sys.path[:0]=[str(C/'02_BACKEND'),str(F/'02_BACKEND'),str(F/'06_TOOLS/EXPERIMENTS/adr_1258')]
from pinned_imports import install,verify_loaded
install(F)
from lawrag.research.experiment_client import ExperimentClient
from lawrag.core.request_deadline import post_json,AbsoluteDeadlineExceeded
import httpx
rows=[];os.environ['OPEN_ROUTER']='synthetic-pinned-key'
with tempfile.TemporaryDirectory() as temporary:
 mock=httpx.MockTransport(lambda request:httpx.Response(200,json={'model':'qwen/qwen3.8-27b','provider':'Parasail','choices':[{'finish_reason':'stop','message':{'content':'{}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1,'cost':0}},request=request))
 client=ExperimentClient(F,Path(temporary),max_calls=2,transport=mock)
 value=super(type(client),client).chat_completions({'model':'qwen/qwen3.8-27b','messages':[{'role':'user','content':'synthetic'}]},phase='test',timeout_seconds=1)
 assert value['status_code']==200 and client.calls==1;rows.append('pinned_reserved_transport_one_mock_call')
assert verify_loaded(F)['verified'];rows.append('all_transport_modules_have_frozen_origins')
try:post_json('https://synthetic.invalid',headers={},json_body={},deadline=time.monotonic()-1);raise AssertionError('deadline ignored')
except AbsoluteDeadlineExceeded as e:assert e.diagnostics['sent'] is False
rows.append('pinned_deadline_pre_dispatch_failure')
from safety import SharedBudget
from semantic_runtime.oracle_dp_io import BudgetPause
s=SharedBudget(2);s.reserve('source');s.reserve('agent')
try:s.reserve('source');raise AssertionError()
except BudgetPause:pass
rows.append('source_agent_shared_budget')
from semantic_runtime.legal_agent.errors import TransportError
assert 'code' not in __import__('inspect').signature(TransportError).parameters;rows.append('transport_error_signature_compatible')
source=(R/read(D/'candidate.json')['entry']).read_text();tree=ast.parse(source);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='guard')
base={'MemAvailable':10*1024**3,'VmRSS':1024**3,'VmSwap':0,'SwapTotal':4*1024**3,'SwapFree':4*1024**3-600*1024**2,'free_disk':100*1024**3}
ns={'resource_lock':threading.RLock(),'measure':lambda:dict(base),'initial_swap':0,'resource_samples':[],'resource_log':None,'time':time,'start':time.monotonic(),'json':json,'os':os};exec(compile(ast.Module(body=[fn],type_ignores=[]),'<frozen guard>','exec'),ns);ns['guard']();assert ns['resource_samples'][-1]['host_swap_growth']==600*1024**2;rows.append('host600MiB_swap_is_allowed')
base['SwapFree']=2*1024**3
try:ns['guard']();raise AssertionError('host cap ignored')
except RuntimeError:assert ns['resource_samples'][-1]['host_swap_growth']==2*1024**3
rows.append('overlimit_sample_saved_before_exception')
from quota_fence import ORIGINAL,CAP
assert CAP==ORIGINAL*.9 and CAP==270*1024**2;rows.append('server_fence_exact_original90percent')
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
write_summary(O/'checks.json',{'passed':len(rows),'failed':0,'checks':rows,'real_model_calls':0,'mock_calls':1,'pinned_binding':verify_loaded(F)});print('Checks',len(rows),'PASS, no real models')
