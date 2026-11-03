"""Exercise actual frozen observer function offline, including its write-once contract."""
from common import *
import ast,time
from types import SimpleNamespace
tree=ast.parse(Path(__file__).with_name('live.py').read_text())
code=compile(ast.Module(body=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in ('gz','recorded_post')],type_ignores=[]),'<actual-observer-functions>','exec')
root=ART/'observer-check';root.mkdir(exist_ok=False)
rows=[]
for label,status in [('success',200),('confirmed-rate-limit',429),('unknown-exception',None)]:
 base=root/label;base.mkdir();calls=[]
 payload={'model':'qwen/qwen3.8-27b','provider':{'only':['parasail/fp8']},'messages':[]}
 response={'choices':[],'usage':{'cost':0.0}}
 def post(url,**kwargs):
  if status is None:raise RuntimeError('offline synthetic transport exception')
  return SimpleNamespace(json=lambda:response,status_code=status,extensions={})
 env=dict(globals(),base=base,calls=calls,active=['request-entry'],current_turn='offline',
  guard=SimpleNamespace(check=lambda:None),t=SimpleNamespace(policy={'endpoint':'https://offline.invalid'}),
  case_id=label,original_post=post)
 exec(code,env)
 try:
  got=env['recorded_post']('https://offline.invalid/chat/completions',json_body=payload)
  assert status is not None and got.status_code==status
 except RuntimeError as exc:
  assert status is None and str(exc)=='offline synthetic transport exception'
 assert not (base/'calls.json').exists()
 put(base/'calls.json',calls)
 folder=base/'raw/call-001';finished=read(folder/'finished.json')
 assert read(folder/'started.json')['status']=='started'
 assert finished==read(base/'calls.json')[0]
 assert finished['status']==('unknown' if status is None else 'responded')
 assert read(folder/'request.json.gz')==payload
 if status is not None:assert read(folder/'response.json.gz')==response
 rows.append({'label':label,'normal_return_or_original_exception':True,'summary_written_once':True,'immutable_start_and_finish':True})
from resource_guard import self_test
put(root/'result.json',{'passed':3,'rows':rows,'resource_guard_checks':self_test(),'actual_model_calls':0})
print('OBSERVER_CHECK_PASS 3; resource guard 8; external calls 0')
