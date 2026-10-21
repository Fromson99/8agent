"""Exhaustive host invariants; records absence on the legacy baseline honestly."""
from pathlib import Path
import gzip,importlib,json,sys
code=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.dont_write_bytecode=True
sys.path.insert(0,str(code/'02_BACKEND'))
try:
 from semantic_runtime.legal_agent import tool_policy as p,tool_outcome as o,errors as e
except ImportError:
 out.write_bytes(gzip.compress(json.dumps({'supported':False,'reason':'baseline has no typed tool outcome/policy contract','cases':[]}).encode(),mtime=0));raise SystemExit(0)
assert Path(p.__file__).is_relative_to(code)
factories={'AUTH':PermissionError,'INTEGRITY':e.ContractError,'STATE':e.StaleProposal,'UNKNOWN':e.TransportError,'INTERNAL':TypeError,'DEADLINE':e.DeadlineExceeded,'BUDGET':e.BudgetExhausted,'PROPOSAL':e.ProposalError,'TRANSIENT':TimeoutError}
rows=[]
for key,spec in p.REGISTRY.items():
 for kind,factory in factories.items():
  for wrapper in ('direct','explicit','implicit'):
   for state in ('normal','stale','deadline','cancelled','no_budget','alternative'):
    err=factory('synthetic private cause')
    if wrapper!='direct':
     outer=e.ToolExecutionError('wrapper')
     if wrapper=='explicit':outer.__cause__=err
     else:outer.__context__=err
     err=outer
    action={'tool':spec.name,'args':{'target':'synthetic-source-A'}}
    outcome=o.exception_outcome(err,action=action,binding_hash='immutable-binding',action_id='a-1',surface=spec.surface)
    current=p.RecoveryState(same_binding=state!='stale',stop_requested=state=='cancelled',distinct_alternative=state=='alternative')
    budget=p.RecoveryBudget(deadline_expired=state=='deadline',investigation_available=state!='no_budget')
    actual=p.choose_recovery(spec,outcome,current,budget)
    expected='OFFER_ALTERNATIVE' if kind=='TRANSIENT' and state=='alternative' and spec.surface=='navigation' else 'STOP'
    passed=(outcome.failure_kind==kind and actual.action==expected and actual.owner==spec.recovery_owner and spec.same_operation_automatic_retries==0 and o.from_dict(outcome.to_dict())==outcome and outcome.operation_key!=o.exception_outcome(err,action={**action,'args':{'target':'synthetic-source-B'}},binding_hash='immutable-binding',action_id='a-1').operation_key)
    rows.append({'choice':'.'.join(key),'cause':kind,'wrapper':wrapper,'state':state,'expected':expected,'actual':actual.action,'contract_correct':passed})
assert len(rows)==5994
out.write_bytes(gzip.compress(json.dumps({'supported':True,'cases':rows},ensure_ascii=False).encode(),mtime=0))
print('cases',len(rows),'passed',sum(x['contract_correct'] for x in rows))
